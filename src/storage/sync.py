"""Best-effort upload of allowlisted terminal summaries."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict
from threading import Event, Lock, Thread
from typing import Protocol
from urllib import error, request

from storage.history import SolveHistory, SolveRecord


PAYLOAD_FIELDS = (
    "session_id",
    "started_at",
    "finished_at",
    "status",
    "facelets_urfdlb",
    "moves",
    "move_count",
    "solve_duration_seconds",
    "error_message",
)
LOCAL_PATH = re.compile(r"(?:(?:[A-Za-z]:\\)|/)[^\s,;]+")
LOGGER = logging.getLogger(__name__)


class SummaryUploader(Protocol):
    def upload(self, payload: dict[str, object]) -> bool: ...


def _safe_error(message: str | None) -> str | None:
    if message is None:
        return None
    return LOCAL_PATH.sub("[local path]", message)[:500]


def build_summary_payload(record: SolveRecord) -> dict[str, object]:
    """Build the only data shape permitted to leave the Raspberry Pi."""
    values = asdict(record)
    values["moves"] = list(record.moves)
    values["move_count"] = len(record.moves)
    values["error_message"] = _safe_error(record.error_message)
    return {field: values[field] for field in PAYLOAD_FIELDS}


class HttpSummaryUploader:
    def __init__(self, endpoint: str, api_key: str, timeout_seconds: float = 3.0):
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> HttpSummaryUploader | None:
        endpoint = os.environ.get("RUBIKS_SYNC_URL")
        api_key = os.environ.get("RUBIKS_SYNC_API_KEY")
        if not endpoint or not api_key:
            return None
        return cls(endpoint, api_key)

    def upload(self, payload: dict[str, object]) -> bool:
        body = json.dumps(payload).encode("utf-8")
        upload_request = request.Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-API-Key": self.api_key,
            },
        )
        try:
            with request.urlopen(
                upload_request, timeout=self.timeout_seconds
            ) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
                return (
                    200 <= response.status < 300 and response_payload.get("ok") is True
                )
        except (
            error.HTTPError,
            error.URLError,
            json.JSONDecodeError,
            OSError,
            TimeoutError,
        ):
            return False


def retry_pending(
    history: SolveHistory, uploader: SummaryUploader | None
) -> tuple[int, int]:
    """Attempt each pending row once, retaining failures for a later run."""
    if uploader is None:
        return 0, 0
    attempted = 0
    synchronized = 0
    for record in history.pending():
        attempted += 1
        if uploader.upload(build_summary_payload(record)):
            history.mark_synced(record.session_id)
            synchronized += 1
    return attempted, synchronized


class RemoteSyncWorker:
    """Retry durable SQLite records without blocking the camera/UI thread.

    SQLite remains the source of truth. The wake event only tells this worker
    that new durable work may be available; no solve payload is held solely in
    memory.
    """

    def __init__(
        self,
        history: SolveHistory,
        uploader: SummaryUploader,
        retry_interval_seconds: float = 10.0,
    ) -> None:
        if retry_interval_seconds <= 0:
            raise ValueError("retry_interval_seconds must be greater than zero")
        self._history = history
        self._uploader = uploader
        self._retry_interval_seconds = retry_interval_seconds
        self._wake_event = Event()
        self._stop_event = Event()
        self._flush_on_stop = Event()
        self._run_lock = Lock()
        self._thread: Thread | None = None

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Start one worker and immediately retry records from earlier runs."""
        if self.is_alive:
            return
        self._stop_event.clear()
        self._flush_on_stop.clear()
        self._wake_event.set()
        self._thread = Thread(target=self._run, name="remote-sync", daemon=True)
        self._thread.start()

    def wake(self) -> None:
        """Non-blockingly notify the worker that SQLite may contain new work."""
        self._wake_event.set()

    def stop(self, flush: bool = True, timeout_seconds: float = 4.0) -> bool:
        """Request shutdown and wait for at most ``timeout_seconds``.

        With ``flush=True`` the worker makes one final attempt after any active
        attempt finishes. A timeout never discards a record because unsent rows
        remain marked pending in SQLite.
        """
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must not be negative")
        thread = self._thread
        if thread is None:
            return True
        if flush:
            self._flush_on_stop.set()
        self._stop_event.set()
        self._wake_event.set()
        thread.join(timeout=timeout_seconds)
        stopped = not thread.is_alive()
        if not stopped:
            LOGGER.warning(
                "Remote sync worker did not stop within %.1f seconds; "
                "pending records remain durable in SQLite",
                timeout_seconds,
            )
        return stopped

    def run_once(self) -> tuple[int, int]:
        """Run one protected retry pass, containing all worker failures."""
        if not self._run_lock.acquire(blocking=False):
            return 0, 0
        try:
            try:
                return retry_pending(self._history, self._uploader)
            except Exception as exc:
                LOGGER.warning(
                    "Unexpected remote sync failure (%s); retry will continue",
                    type(exc).__name__,
                )
                return 0, 0
        finally:
            self._run_lock.release()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._wake_event.wait(self._retry_interval_seconds)
            self._wake_event.clear()
            if self._stop_event.is_set():
                break
            self.run_once()

        if self._flush_on_stop.is_set():
            self.run_once()
