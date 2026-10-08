import argparse
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import app
from cube.solver import SOLVED_STATE
from storage.history import SolveHistory, SolveRecord
from vision.face_scan import ScanOutcome


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

    def row_count(self) -> int:
        with sqlite3.connect(self.database) as connection:
            return connection.execute("SELECT COUNT(*) FROM solve_runs").fetchone()[0]

    def patches(self, uploader=None):
        return (
            mock.patch.object(app, "parse_args", return_value=self.arguments),
            mock.patch.object(
                app.HttpSummaryUploader, "from_environment", return_value=uploader
            ),
            mock.patch.object(app, "create_camera", return_value=object()),
        )

    def test_complete_run_is_recorded(self) -> None:
        def solved_scan(_camera, _output, validator, **_kwargs):
            outcome = ScanOutcome(SOLVED_STATE)
            validator(outcome)
            return outcome

        parse, uploader, camera = self.patches()
        with (
            parse,
            uploader,
            camera,
            mock.patch.object(app, "scan_cube", side_effect=solved_scan),
            mock.patch.object(app, "show_guidance", return_value="COMPLETE"),
        ):
            app.main()
        self.assertEqual(self.status(), ("COMPLETE", 0, None))
        self.assertEqual(self.row_count(), 1)

    def test_scan_cancellation_is_recorded(self) -> None:
        parse, uploader, camera = self.patches()
        with (
            parse,
            uploader,
            camera,
            mock.patch.object(app, "scan_cube", return_value=None),
        ):
            app.main()
        self.assertEqual(self.status(), ("CANCELLED", 0, None))
        self.assertEqual(self.row_count(), 1)

    def test_camera_error_is_recorded_and_returns_failure(self) -> None:
        parse, uploader, _camera = self.patches()
        with (
            parse,
            uploader,
            mock.patch.object(
                app, "create_camera", side_effect=RuntimeError("camera unavailable")
            ),
            self.assertRaises(SystemExit),
        ):
            app.main()
        self.assertEqual(self.status(), ("ERROR", 0, "camera unavailable"))
        self.assertEqual(self.row_count(), 1)

    def test_blocked_uploader_does_not_delay_scanner_entry(self) -> None:
        upload_started = threading.Event()
        release_upload = threading.Event()
        scanner_started = threading.Event()
        failures: list[BaseException] = []

        class BlockingUploader:
            def upload(self, _payload: dict[str, object]) -> bool:
                upload_started.set()
                release_upload.wait(2.0)
                return True

        history = SolveHistory(self.database)
        history.record(
            SolveRecord(
                session_id="pending-from-earlier-run",
                started_at="2026-10-04T00:00:00+00:00",
                finished_at="2026-10-04T00:00:01+00:00",
                status="COMPLETE",
                facelets_urfdlb=None,
                moves=(),
                solve_duration_seconds=None,
                error_message=None,
            )
        )

        def cancelled_scan(*_args, **_kwargs):
            scanner_started.set()
            return None

        def run_application() -> None:
            try:
                app.main()
            except BaseException as exc:  # pragma: no cover - assertion reports details
                failures.append(exc)

        parse, uploader, camera = self.patches(BlockingUploader())
        with (
            parse,
            uploader,
            camera,
            mock.patch.object(app, "scan_cube", side_effect=cancelled_scan),
        ):
            application_thread = threading.Thread(target=run_application)
            application_thread.start()
            self.assertTrue(upload_started.wait(1.0))
            self.assertTrue(scanner_started.wait(1.0))
            release_upload.set()
            application_thread.join(2.0)

        self.assertFalse(application_thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(self.row_count(), 2)


if __name__ == "__main__":
    unittest.main()
