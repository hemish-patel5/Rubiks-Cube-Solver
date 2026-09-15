"""Exercise the real dashboard handler over HTTP using a temporary SQLite PDO.

Requires PHP CLI with pdo_sqlite. This verifies browser actions and SQL deletion;
target-host MariaDB permissions still need deployment acceptance testing.
"""

import http.cookiejar
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from urllib import error, parse, request


class DashboardHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.php = os.environ.get("PHP_BINARY") or shutil.which("php")
        if not cls.php:
            raise unittest.SkipTest("PHP CLI is not installed")
        probe = subprocess.run(
            [cls.php, "-r", "echo json_encode(PDO::getAvailableDrivers());"],
            capture_output=True, text=True,
        )
        if probe.returncode or "sqlite" not in json.loads(probe.stdout):
            raise unittest.SkipTest("PHP pdo_sqlite is required")

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.dashboard_path = root / "index.php"
        self.database = root / "history.db"
        with sqlite3.connect(self.database) as db:
            db.execute("""CREATE TABLE solve_runs (
                session_id TEXT PRIMARY KEY, finished_at TEXT,
                terminal_status TEXT, move_count INTEGER,
                solve_duration_seconds REAL, error_message TEXT
            )""")
            db.executemany("INSERT INTO solve_runs VALUES (?, ?, ?, ?, ?, ?)", [
                (f"session-{index:02}", "2026-09-15 12:00:00", "COMPLETE", 20, 30, None)
                for index in range(26)
            ])
            db.execute("UPDATE solve_runs SET terminal_status='ERROR', error_message='camera failed' WHERE session_id='session-25'")
        source = (Path(__file__).parents[1] / "web/index.php").read_text()
        self.api_key = re.search(r"const DASHBOARD_API_KEY = '([^']+)'", source)[1]
        # Run the production handler unchanged apart from selecting SQLite PDO.
        source = source.replace("declare(strict_types=1);", """declare(strict_types=1);
namespace DashboardFixture;
use \\Throwable;
use \\RuntimeException;
class PDO extends \\PDO {
    public function __construct($dsn, $username, $password, $options) {
        parent::__construct('sqlite:' . getenv('TEST_DATABASE'), null, null, $options);
    }
}
""", 1)
        (root / "index.php").write_text(source)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{port}/index.php"
        environment = os.environ.copy()
        environment.update(
            TEST_DATABASE=str(self.database), RUBIKS_DB_NAME="test",
            RUBIKS_DB_READ_USER="test", RUBIKS_DB_READ_PASSWORD="test",
            RUBIKS_API_KEY=self.api_key,
        )
        self.server = subprocess.Popen(
            [self.php, "-d", f"session.save_path={root}", "-S", f"127.0.0.1:{port}", "-t", str(root)],
            env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.addCleanup(self.stop_server)
        self.client = request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        for _ in range(100):
            try:
                self.get()
                break
            except error.URLError:
                if self.server.poll() is not None:
                    self.fail("PHP test server failed to start")
                time.sleep(0.02)
        else:
            self.fail("PHP test server did not become ready")

    def stop_server(self) -> None:
        self.server.terminate()
        self.server.wait(timeout=5)

    def get(self, suffix="") -> str:
        with self.client.open(self.url + suffix, timeout=5) as response:
            return response.read().decode()

    def token(self) -> str:
        return re.search(r'name="csrf_token" value="([a-f0-9]+)"', self.get())[1]

    def post(self, **fields) -> str:
        with self.client.open(self.url, data=parse.urlencode(fields).encode(), timeout=5) as response:
            return response.read().decode()

    def count(self) -> int:
        with sqlite3.connect(self.database) as db:
            return db.execute("SELECT COUNT(*) FROM solve_runs").fetchone()[0]

    def test_removal_updates_rows_statistics_errors_and_pagination(self) -> None:
        page = self.get()
        self.assertIn("Page 1 of 2", page)
        self.assertNotIn(self.api_key, page)
        self.assertNotIn("Enable removal", page)
        self.assertNotIn('name="api_key"', page)
        self.assertIn("camera failed", page)
        self.assertIn("session-00", self.get("?page=2"))
        page = self.post(action="delete", session_id="session-25", csrf_token=self.token())
        self.assertEqual(self.count(), 25)
        self.assertNotIn("session-25", page)
        self.assertNotIn("camera failed", page)
        self.assertIn('Total attempts<span class="value">25</span>', page)
        self.assertIn("Page 1 of 1", page)
        self.get()  # Reload does not delete another row.
        self.assertEqual(self.count(), 25)
        page = self.post(action="delete", session_id="session-25", csrf_token=self.token())
        self.assertIn("already removed", page)

    def test_invalid_csrf_and_session_ids_cannot_delete(self) -> None:
        with self.assertRaises(error.HTTPError) as caught:
            self.post(action="delete", session_id="session-25", csrf_token="incorrect")
        self.assertEqual(caught.exception.code, 403)
        self.assertEqual(self.count(), 26)

        with self.assertRaises(error.HTTPError) as caught:
            self.post(action="delete", session_id="' OR 1=1 --", csrf_token=self.token())
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.count(), 26)
        with self.assertRaises(error.HTTPError) as caught:
            self.post(action="delete", session_id="session-25")
        self.assertEqual(caught.exception.code, 403)
        self.assertEqual(self.count(), 26)

    def test_mismatched_server_key_blocks_removal(self) -> None:
        source = self.dashboard_path.read_text()
        self.dashboard_path.write_text(source.replace(self.api_key, "different-server-key"))
        self.assertIn("Removal unavailable", self.get())
        with self.assertRaises(error.HTTPError) as caught:
            self.post(action="delete", session_id="session-25", csrf_token=self.token())
        self.assertEqual(caught.exception.code, 403)
        self.assertEqual(self.count(), 26)
