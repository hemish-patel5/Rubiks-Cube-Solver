"""Run the 3x3 scanner, physical-state validation, and solver handoff."""

from __future__ import annotations

import argparse
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scan-mode",
        choices=("angled-sides", "motorized-angled", "head-on"),
        default="angled-sides",
        help="camera workflow (motorized-angled rotates the platform automatically)",
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
    parser.add_argument("--motor-in1-pin", type=int, default=17)
    parser.add_argument("--motor-in2-pin", type=int, default=18)
    parser.add_argument("--motor-in3-pin", type=int, default=27)
    parser.add_argument("--motor-in4-pin", type=int, default=22)
    parser.add_argument(
        "--motor-direction",
        choices=("clockwise", "counterclockwise"),
        default="clockwise",
    )
    parser.add_argument("--motor-start-rate", type=int, default=300)
    parser.add_argument("--motor-cruise-rate", type=int, default=900)
    parser.add_argument("--motor-ramp-steps", type=int, default=128)
    parser.add_argument("--motor-steps-per-revolution", type=int, default=4_096)
    parser.add_argument("--motor-settle-seconds", type=float, default=1.0)
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
    platform = None
    try:
        if args.scan_mode == "motorized-angled":
            platform = create_stepper_platform(
                in1_pin=args.motor_in1_pin,
                in2_pin=args.motor_in2_pin,
                in3_pin=args.motor_in3_pin,
                in4_pin=args.motor_in4_pin,
                clockwise=args.motor_direction == "clockwise",
                start_rate=args.motor_start_rate,
                cruise_rate=args.motor_cruise_rate,
                quarter_ramp_steps=args.motor_ramp_steps,
                steps_per_revolution=args.motor_steps_per_revolution,
            )
        camera = create_camera(args.backend, args.device)

        def validate_and_solve(outcome: ScanOutcome) -> None:
            nonlocal facelets, moves
            facelets = outcome.facelets_urfdlb
            moves = solve_3x3(facelets)

        outcome = scan_cube(
            camera,
            args.output,
            validate_and_solve,
            mode=args.scan_mode,
            platform=platform,
            motor_settle_seconds=getattr(args, "motor_settle_seconds", 1.0),
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
