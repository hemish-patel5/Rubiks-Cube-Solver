"""Best-effort upload of allowlisted terminal summaries."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
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
                return 200 <= response.status < 300 and response_payload.get("ok") is True
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
