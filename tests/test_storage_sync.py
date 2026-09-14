import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from storage.history import SolveHistory, SolveRecord
from storage import sync
from storage.sync import (
    PAYLOAD_FIELDS,
    HttpSummaryUploader,
    build_summary_payload,
    retry_pending,
)


def record(session_id: str, status: str, **overrides: object) -> SolveRecord:
    values = {
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
        with mock.patch.object(sync.request, "urlopen", return_value=Response()) as open_url:
            uploaded = uploader.upload({"session_id": "session"})
        upload_request = open_url.call_args.args[0]
        self.assertTrue(uploaded)
        self.assertEqual(open_url.call_args.kwargs["timeout"], 2.5)
        self.assertEqual(upload_request.get_header("X-api-key"), "secret")
        self.assertEqual(upload_request.get_method(), "POST")


if __name__ == "__main__":
    unittest.main()
