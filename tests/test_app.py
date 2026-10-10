import sqlite3
import sys
import tempfile
import threading
import unittest
from contextlib import ExitStack, contextmanager
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
        self.output = Path(self.temporary.name) / "scan"

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

    @contextmanager
    def runtime(self, uploader=None):
        platform = mock.Mock()
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(app, "DATABASE_PATH", self.database))
            stack.enter_context(mock.patch.object(app, "OUTPUT_DIR", self.output))
            stack.enter_context(
                mock.patch.object(
                    app.HttpSummaryUploader,
                    "from_environment",
                    return_value=uploader,
                )
            )
            camera = stack.enter_context(
                mock.patch.object(app, "create_camera", return_value=object())
            )
            create_platform = stack.enter_context(
                mock.patch.object(
                    app, "create_stepper_platform", return_value=platform
                )
            )
            yield platform, camera, create_platform

    def test_complete_run_is_recorded(self) -> None:
        def solved_scan(_camera, _output, validator, **_kwargs):
            outcome = ScanOutcome(SOLVED_STATE)
            validator(outcome)
            return outcome

        runtime = self.runtime()
        with (
            runtime,
            mock.patch.object(app, "scan_cube", side_effect=solved_scan),
            mock.patch.object(app, "show_guidance", return_value="COMPLETE"),
        ):
            app.main()
        self.assertEqual(self.status(), ("COMPLETE", 0, None))
        self.assertEqual(self.row_count(), 1)

    def test_scan_cancellation_is_recorded(self) -> None:
        runtime = self.runtime()
        with (
            runtime,
            mock.patch.object(app, "scan_cube", return_value=None),
        ):
            app.main()
        self.assertEqual(self.status(), ("CANCELLED", 0, None))
        self.assertEqual(self.row_count(), 1)

    def test_main_uses_motorized_opencv_workflow_and_closes_platform(self) -> None:
        runtime = self.runtime()
        with (
            runtime as (platform, camera, create_platform),
            mock.patch.object(app, "scan_cube", return_value=None) as scan,
        ):
            app.main()

        create_platform.assert_called_once_with()
        camera.assert_called_once_with("opencv", 0)
        self.assertEqual(scan.call_args.args[1], self.output)
        self.assertEqual(scan.call_args.kwargs["mode"], "motorized-angled")
        self.assertIs(scan.call_args.kwargs["platform"], platform)
        self.assertEqual(scan.call_args.kwargs["motor_settle_seconds"], 1.0)
        platform.close.assert_called_once_with()

    def test_camera_error_is_recorded_and_returns_failure(self) -> None:
        platform = mock.Mock()
        with (
            mock.patch.object(app, "DATABASE_PATH", self.database),
            mock.patch.object(app, "OUTPUT_DIR", self.output),
            mock.patch.object(
                app.HttpSummaryUploader, "from_environment", return_value=None
            ),
            mock.patch.object(
                app, "create_stepper_platform", return_value=platform
            ),
            mock.patch.object(
                app, "create_camera", side_effect=RuntimeError("camera unavailable")
            ),
            self.assertRaises(SystemExit),
        ):
            app.main()
        self.assertEqual(self.status(), ("ERROR", 0, "camera unavailable"))
        self.assertEqual(self.row_count(), 1)
        platform.close.assert_called_once_with()

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

        runtime = self.runtime(BlockingUploader())
        with (
            runtime,
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
