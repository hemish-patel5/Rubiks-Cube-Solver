import argparse
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import app
from cube.solver import SOLVED_STATE
from vision.face_scan import ScanOutcome


class FakeControls:
    def show_status(self, _status: str, _detail: str = "") -> None:
        pass


class ApplicationTerminalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "history.db"
        self.arguments = argparse.Namespace(
            scan_mode="angled-sides",
            backend="auto",
            device=0,
            output=Path(self.temporary.name) / "scan",
            database=self.database,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def status(self) -> tuple[str, int, str | None]:
        with sqlite3.connect(self.database) as connection:
            return connection.execute(
                "SELECT terminal_status, move_count, error_message FROM solve_runs"
            ).fetchone()

    def patches(self):
        return (
            mock.patch.object(app, "parse_args", return_value=self.arguments),
            mock.patch.object(app, "SenseHatAdapter", return_value=FakeControls()),
            mock.patch.object(app.HttpSummaryUploader, "from_environment", return_value=None),
            mock.patch.object(app, "create_camera", return_value=object()),
        )

    def test_complete_run_is_recorded(self) -> None:
        def solved_scan(_camera, _output, validator, _controls, **_kwargs):
            outcome = ScanOutcome(SOLVED_STATE)
            validator(outcome)
            return outcome

        parse, controls, uploader, camera = self.patches()
        with parse, controls, uploader, camera, mock.patch.object(
            app, "scan_cube", side_effect=solved_scan
        ), mock.patch.object(app, "show_guidance", return_value="COMPLETE"):
            app.main()
        self.assertEqual(self.status(), ("COMPLETE", 0, None))

    def test_scan_cancellation_is_recorded(self) -> None:
        parse, controls, uploader, camera = self.patches()
        with parse, controls, uploader, camera, mock.patch.object(
            app, "scan_cube", return_value=None
        ):
            app.main()
        self.assertEqual(self.status(), ("CANCELLED", 0, None))

    def test_camera_error_is_recorded_and_returns_failure(self) -> None:
        parse, controls, uploader, _camera = self.patches()
        with parse, controls, uploader, mock.patch.object(
            app, "create_camera", side_effect=RuntimeError("camera unavailable")
        ), self.assertRaises(SystemExit):
            app.main()
        self.assertEqual(self.status(), ("ERROR", 0, "camera unavailable"))


if __name__ == "__main__":
    unittest.main()
