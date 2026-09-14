"""Run the 3x3 scanner, physical-state validation, and solver handoff."""

from __future__ import annotations

import argparse
from pathlib import Path

from cube.solver import solve_3x3
from vision.face_scan import ScanOutcome, create_camera, scan_cube


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
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
    try:
        camera = create_camera(args.backend, args.device)
    except RuntimeError as exc:
        raise SystemExit(f"Camera error: {exc}") from exc

    moves: list[str] | None = None

    def validate_and_solve(outcome: ScanOutcome) -> None:
        nonlocal moves
        moves = solve_3x3(outcome.facelets_urfdlb)

    outcome = scan_cube(camera, args.output, validate_and_solve)
    if outcome is None:
        print("Scan cancelled")
        return
    print("Solution:", " ".join(moves or []) or "already solved (0 moves)")


if __name__ == "__main__":
    main()
