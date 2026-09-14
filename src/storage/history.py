"""SQLite persistence for one terminal record per assistant run."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


TERMINAL_STATUSES = {"COMPLETE", "ERROR", "CANCELLED"}


@dataclass(frozen=True)
class SolveRecord:
    session_id: str
    started_at: str
    finished_at: str
    status: str
    facelets_urfdlb: str | None
    moves: tuple[str, ...]
    solve_duration_seconds: float | None
    error_message: str | None
    synced: bool = False

    def __post_init__(self) -> None:
        if self.status not in TERMINAL_STATUSES:
            raise ValueError(f"status must be one of {sorted(TERMINAL_STATUSES)}")


SCHEMA = """
CREATE TABLE IF NOT EXISTS solve_runs (
    session_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    terminal_status TEXT NOT NULL
        CHECK (terminal_status IN ('COMPLETE', 'ERROR', 'CANCELLED')),
    facelets_urfdlb TEXT,
    moves_json TEXT NOT NULL,
    move_count INTEGER NOT NULL CHECK (move_count >= 0),
    solve_duration_seconds REAL,
    error_message TEXT,
    synced INTEGER NOT NULL DEFAULT 0 CHECK (synced IN (0, 1))
)
"""


class SolveHistory:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(SCHEMA)

    def record(self, record: SolveRecord) -> None:
        self.initialize()
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO solve_runs (
                    session_id, started_at, finished_at, terminal_status,
                    facelets_urfdlb, moves_json, move_count,
                    solve_duration_seconds, error_message, synced
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    started_at = excluded.started_at,
                    finished_at = excluded.finished_at,
                    terminal_status = excluded.terminal_status,
                    facelets_urfdlb = excluded.facelets_urfdlb,
                    moves_json = excluded.moves_json,
                    move_count = excluded.move_count,
                    solve_duration_seconds = excluded.solve_duration_seconds,
                    error_message = excluded.error_message,
                    synced = excluded.synced
                """,
                (
                    record.session_id,
                    record.started_at,
                    record.finished_at,
                    record.status,
                    record.facelets_urfdlb,
                    json.dumps(record.moves),
                    len(record.moves),
                    record.solve_duration_seconds,
                    record.error_message,
                    int(record.synced),
                ),
            )

    def pending(self) -> list[SolveRecord]:
        self.initialize()
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT session_id, started_at, finished_at, terminal_status,
                       facelets_urfdlb, moves_json, solve_duration_seconds,
                       error_message, synced
                FROM solve_runs
                WHERE synced = 0
                ORDER BY finished_at, session_id
                """
            ).fetchall()
        return [
            SolveRecord(
                session_id=row[0],
                started_at=row[1],
                finished_at=row[2],
                status=row[3],
                facelets_urfdlb=row[4],
                moves=tuple(json.loads(row[5])),
                solve_duration_seconds=row[6],
                error_message=row[7],
                synced=bool(row[8]),
            )
            for row in rows
        ]

    def mark_synced(self, session_id: str) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "UPDATE solve_runs SET synced = 1 WHERE session_id = ?",
                (session_id,),
            )
