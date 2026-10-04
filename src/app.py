"""Run the 3x3 scanner, physical-state validation, and solver handoff."""

from __future__ import annotations

import argparse
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cube.solver import solve_3x3
from hardware.sense_hat_adapter import SenseHatAdapter
from interface.guidance import show_guidance
from storage.history import SolveHistory, SolveRecord
from storage.sync import HttpSummaryUploader, RemoteSyncWorker
from vision.face_scan import ScanOutcome, create_camera, scan_cube


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scan-mode",
        choices=("angled-sides", "head-on"),
        default="angled-sides",
        help="camera workflow (default: angled views with inferred bottom face)",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "opencv", "picamera2"),
        default="auto",
        help="camera API (default: try OpenCV webcam, then Picamera2)",
    )
    parser.add_argument(
        "--device", type=int, default=0, help="OpenCV webcam device number"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("scan_output"),
        help="directory for cube_state.json and six face images",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/solve_history.db"),
        help="SQLite history database (used by the complete application)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    history = SolveHistory(args.database)
    history.initialize()
    uploader = HttpSummaryUploader.from_environment()
    sync_worker = RemoteSyncWorker(history, uploader) if uploader else None
    if sync_worker:
        sync_worker.start()

    session_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    facelets: str | None = None
    moves: list[str] = []
    solve_duration_seconds: float | None = None
    terminal_status = "ERROR"
    error_message: str | None = None
    controls = SenseHatAdapter()
    controls.show_status("ready")

    try:
        camera = create_camera(args.backend, args.device)

        def validate_and_solve(outcome: ScanOutcome) -> None:
            nonlocal facelets, moves
            facelets = outcome.facelets_urfdlb
            moves = solve_3x3(facelets)

        outcome = scan_cube(
            camera, args.output, validate_and_solve, controls, mode=args.scan_mode
        )
        if outcome is None:
            terminal_status = "CANCELLED"
            print("Scan cancelled")
        else:
            print("Solution:", " ".join(moves) or "already solved (0 moves)")
            solve_started = time.monotonic()
            try:
                terminal_status = show_guidance(moves, controls)
            finally:
                solve_duration_seconds = time.monotonic() - solve_started
            print("Guidance:", terminal_status)
    except Exception as exc:
        controls.show_status("error")
        terminal_status = "ERROR"
        error_message = str(exc)
        print(f"Application error: {exc}")
    finally:
        try:
            history.record(
                SolveRecord(
                    session_id=session_id,
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    status=terminal_status,
                    facelets_urfdlb=facelets,
                    moves=tuple(moves),
                    solve_duration_seconds=solve_duration_seconds,
                    error_message=error_message,
                )
            )
        finally:
            if sync_worker:
                sync_worker.wake()
                sync_worker.stop(flush=True, timeout_seconds=4.0)

    if terminal_status == "ERROR":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
