import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from storage.history import SolveHistory, SolveRecord
from storage import sync
from storage.sync import (
    PAYLOAD_FIELDS,
    HttpSummaryUploader,
    RemoteSyncWorker,
    build_summary_payload,
    retry_pending,
)


def record(session_id: str, status: str, **overrides: object) -> SolveRecord:
    values: dict[str, object] = {
        "session_id": session_id,
        "started_at": "2026-09-15T01:00:00+00:00",
        "finished_at": "2026-09-15T01:00:01+00:00",
        "status": status,
        "facelets_urfdlb": None,
        "moves": (),
        "solve_duration_seconds": None,
        "error_message": None,
    }
    values.update(overrides)
    return SolveRecord(**values)  # type: ignore[arg-type]


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "history.db"
        self.history = SolveHistory(self.database)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_complete_error_and_cancelled_terminal_rows(self) -> None:
        self.history.record(record("complete", "COMPLETE", moves=("R", "U")))
        self.history.record(record("error", "ERROR", error_message="camera failed"))
        self.history.record(record("cancelled", "CANCELLED"))
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                "SELECT terminal_status, move_count, synced FROM solve_runs ORDER BY session_id"
            ).fetchall()
        self.assertEqual(
            rows,
            [("CANCELLED", 0, 0), ("COMPLETE", 2, 0), ("ERROR", 0, 0)],
        )

    def test_session_id_is_idempotent(self) -> None:
        self.history.record(record("same-session", "ERROR", error_message="first"))
        self.history.record(record("same-session", "CANCELLED"))
        with sqlite3.connect(self.database) as connection:
            count, status = connection.execute(
                "SELECT COUNT(*), terminal_status FROM solve_runs"
            ).fetchone()
        self.assertEqual(count, 1)
        self.assertEqual(status, "CANCELLED")

    def test_terminal_row_contains_required_summary_fields(self) -> None:
        facelets = "".join(face * 9 for face in "URFDLB")
        self.history.record(
            record(
                "full-row",
                "COMPLETE",
                facelets_urfdlb=facelets,
                moves=("R", "U'"),
                solve_duration_seconds=12.5,
            )
        )
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                """
                SELECT started_at, finished_at, facelets_urfdlb, moves_json,
                       move_count, solve_duration_seconds, error_message, synced
                FROM solve_runs WHERE session_id = ?
                """,
                ("full-row",),
            ).fetchone()
        self.assertEqual(row[0], "2026-09-15T01:00:00+00:00")
        self.assertEqual(row[1], "2026-09-15T01:00:01+00:00")
        self.assertEqual(row[2], facelets)
        self.assertEqual(row[3], '["R", "U\'"]')
        self.assertEqual(row[4:], (2, 12.5, None, 0))


class SyncTests(unittest.TestCase):
    def test_payload_is_allowlisted_and_redacts_local_paths(self) -> None:
        summary = build_summary_payload(
            record(
                "session",
                "ERROR",
                error_message=(
                    "failed at /Users/example/scan_output/face_U.jpg "
                    "and C:\\captures\\face_U.jpg"
                ),
            )
        )
        self.assertEqual(tuple(summary), PAYLOAD_FIELDS)
        self.assertNotIn("synced", summary)
        self.assertNotIn("samples", summary)
        self.assertNotIn("/Users/", str(summary))
        self.assertNotIn("C:\\captures", str(summary))

    def test_failed_retry_keeps_row_pending(self) -> None:
        class FailedUploader:
            def __init__(self) -> None:
                self.calls = 0

            def upload(self, _payload: dict[str, object]) -> bool:
                self.calls += 1
                return False

        with tempfile.TemporaryDirectory() as directory:
            history = SolveHistory(Path(directory) / "history.db")
            history.record(record("pending", "COMPLETE"))
            uploader = FailedUploader()
            attempted, synchronized = retry_pending(history, uploader)
            pending = history.pending()
        self.assertEqual((attempted, synchronized), (1, 0))
        self.assertEqual(uploader.calls, 1)
        self.assertEqual([item.session_id for item in pending], ["pending"])

    def test_successful_retry_marks_row_synchronized(self) -> None:
        class SuccessfulUploader:
            def upload(self, _payload: dict[str, object]) -> bool:
                return True

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "history.db"
            history = SolveHistory(database)
            history.record(record("uploaded", "COMPLETE"))
            result = retry_pending(history, SuccessfulUploader())
            with sqlite3.connect(database) as connection:
                synced = connection.execute(
                    "SELECT synced FROM solve_runs WHERE session_id = ?",
                    ("uploaded",),
                ).fetchone()[0]
        self.assertEqual(result, (1, 1))
        self.assertEqual(synced, 1)

    def test_http_uploader_uses_api_key_and_short_timeout(self) -> None:
        class Response:
            status = 200

            def read(self) -> bytes:
                return b'{"ok": true}'

            def __enter__(self):
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        uploader = HttpSummaryUploader(
            "https://lamp.example/api/sessions.php", "secret", timeout_seconds=2.5
        )
        with mock.patch.object(
            sync.request, "urlopen", return_value=Response()
        ) as open_url:
            uploaded = uploader.upload({"session_id": "session"})
        upload_request = open_url.call_args.args[0]
        self.assertTrue(uploaded)
        self.assertEqual(open_url.call_args.kwargs["timeout"], 2.5)
        self.assertEqual(upload_request.get_header("X-api-key"), "secret")
        self.assertEqual(upload_request.get_method(), "POST")


class RemoteSyncWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.history = SolveHistory(Path(self.temporary.name) / "history.db")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_successful_background_upload_marks_row_synchronized(self) -> None:
        uploaded = threading.Event()

        class SuccessfulUploader:
            def upload(self, _payload: dict[str, object]) -> bool:
                uploaded.set()
                return True

        self.history.record(record("background-success", "COMPLETE"))
        worker = RemoteSyncWorker(self.history, SuccessfulUploader())
        worker.start()
        self.assertTrue(uploaded.wait(1.0))
        self.assertTrue(worker.stop())
        self.assertEqual(self.history.pending(), [])

    def test_failed_upload_remains_pending_and_worker_survives(self) -> None:
        attempted = threading.Event()

        class FailedUploader:
            def upload(self, _payload: dict[str, object]) -> bool:
                attempted.set()
                return False

        self.history.record(record("background-failure", "COMPLETE"))
        worker = RemoteSyncWorker(self.history, FailedUploader())
        worker.start()
        self.assertTrue(attempted.wait(1.0))
        self.assertTrue(worker.is_alive)
        self.assertTrue(worker.stop(flush=False))
        self.assertEqual(
            [item.session_id for item in self.history.pending()],
            ["background-failure"],
        )

    def test_unexpected_uploader_exception_does_not_kill_worker(self) -> None:
        attempted = threading.Event()

        class RaisingUploader:
            def upload(self, _payload: dict[str, object]) -> bool:
                attempted.set()
                raise RuntimeError("unexpected uploader failure")

        self.history.record(record("unexpected-failure", "COMPLETE"))
        worker = RemoteSyncWorker(self.history, RaisingUploader())
        worker.start()
        self.assertTrue(attempted.wait(1.0))
        self.assertTrue(worker.is_alive)
        self.assertTrue(worker.stop(flush=False))
        self.assertEqual(
            [item.session_id for item in self.history.pending()],
            ["unexpected-failure"],
        )

    def test_stop_flushes_record_created_immediately_before_shutdown(self) -> None:
        class SuccessfulUploader:
            def upload(self, _payload: dict[str, object]) -> bool:
                return True

        worker = RemoteSyncWorker(self.history, SuccessfulUploader())
        worker.start()
        self.history.record(record("last-record", "COMPLETE"))
        worker.wake()
        self.assertTrue(worker.stop(flush=True))
        self.assertEqual(self.history.pending(), [])

    def test_repeated_start_and_wake_do_not_duplicate_active_upload(self) -> None:
        upload_started = threading.Event()
        release_upload = threading.Event()
        calls_lock = threading.Lock()
        calls = 0

        class BlockingUploader:
            def upload(self, _payload: dict[str, object]) -> bool:
                nonlocal calls
                with calls_lock:
                    calls += 1
                upload_started.set()
                release_upload.wait(1.0)
                return True

        self.history.record(record("one-upload", "COMPLETE"))
        worker = RemoteSyncWorker(self.history, BlockingUploader())
        worker.start()
        self.assertTrue(upload_started.wait(1.0))
        worker.start()
        remote_threads = [
            thread for thread in threading.enumerate() if thread.name == "remote-sync"
        ]
        self.assertEqual(len(remote_threads), 1)
        self.assertTrue(remote_threads[0].daemon)
        for _ in range(5):
            worker.wake()
        with calls_lock:
            self.assertEqual(calls, 1)
        release_upload.set()
        self.assertTrue(worker.stop())
        with calls_lock:
            self.assertEqual(calls, 1)

    def test_stop_timeout_is_bounded_and_keeps_pending_record(self) -> None:
        upload_started = threading.Event()
        release_upload = threading.Event()

        class BlockingUploader:
            def upload(self, _payload: dict[str, object]) -> bool:
                upload_started.set()
                release_upload.wait(1.0)
                return False

        self.history.record(record("slow-upload", "COMPLETE"))
        worker = RemoteSyncWorker(self.history, BlockingUploader())
        worker.start()
        self.assertTrue(upload_started.wait(1.0))
        started = time.monotonic()
        self.assertFalse(worker.stop(flush=False, timeout_seconds=0.05))
        self.assertLess(time.monotonic() - started, 0.5)
        release_upload.set()
        self.assertTrue(worker.stop(flush=False, timeout_seconds=1.0))
        self.assertEqual(
            [item.session_id for item in self.history.pending()],
            ["slow-upload"],
        )


if __name__ == "__main__":
    unittest.main()
