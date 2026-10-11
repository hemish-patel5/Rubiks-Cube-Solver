"""Run the 3x3 scanner, physical-state validation, and solver handoff."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cube.solver import solve_3x3
from hardware.stepper_spin import create_stepper_platform
from interface.guidance import show_guidance
from storage.history import SolveHistory, SolveRecord
from storage.sync import HttpSummaryUploader, RemoteSyncWorker
from vision.face_scan import ScanOutcome, create_camera, scan_cube


CAMERA_BACKEND = "opencv"
CAMERA_DEVICE = 0
OUTPUT_DIR = Path("scan_output")
DATABASE_PATH = Path("data/solve_history.db")
MOTOR_SETTLE_SECONDS = 1.0


def main() -> None:
    history = SolveHistory(DATABASE_PATH)
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
    platform = None
    try:
        platform = create_stepper_platform()
        camera = create_camera(CAMERA_BACKEND, CAMERA_DEVICE)

        def validate_and_solve(outcome: ScanOutcome) -> None:
            nonlocal facelets, moves
            facelets = outcome.facelets_urfdlb
            moves = solve_3x3(facelets)

        outcome = scan_cube(
            camera,
            OUTPUT_DIR,
            validate_and_solve,
            mode="motorized-angled",
            platform=platform,
            motor_settle_seconds=MOTOR_SETTLE_SECONDS,
        )
        if outcome is None:
            terminal_status = "CANCELLED"
            print("Scan cancelled")
        else:
            print("Solution:", " ".join(moves) or "already solved (0 moves)")
            solve_started = time.monotonic()
            try:
                terminal_status = show_guidance(moves)
            finally:
                solve_duration_seconds = time.monotonic() - solve_started
            print("Guidance:", terminal_status)
    except Exception as exc:
        terminal_status = "ERROR"
        error_message = str(exc)
        print(f"Application error: {exc}")
    finally:
        try:
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
                if platform is not None:
                    platform.close()
        finally:
            if sync_worker:
                sync_worker.wake()
                sync_worker.stop(flush=True, timeout_seconds=4.0)

    if terminal_status == "ERROR":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
