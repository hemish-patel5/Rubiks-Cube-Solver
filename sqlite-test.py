import sqlite3
from pathlib import Path

path = Path("data/solve_history.db")
if not path.exists():
    raise SystemExit("History Databse was not created")

with sqlite3.connect(path) as db:
    rows  = db.execute("""
        SELECT terminal_status, move_count, synced, session_id
        FROM solve_runs
        ORDER BY finished_at DESC
        LIMIT 5
    """).fetchall()
    
for status, moves, synced, session in rows:
    print(f"{status} | moves={moves} | synced={synced} | {session}")
    
    
    