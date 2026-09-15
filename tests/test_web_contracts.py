import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
ENDPOINT = (ROOT / "web/api/sessions.php").read_text(encoding="utf-8")
SCHEMA = (ROOT / "web/schema.sql").read_text(encoding="utf-8")
DASHBOARD = (ROOT / "web/index.php").read_text(encoding="utf-8")


class LampContractTests(unittest.TestCase):
    def test_endpoint_requires_environment_api_key_and_prepared_write(self) -> None:
        self.assertIn("getenv('RUBIKS_API_KEY')", ENDPOINT)
        self.assertIn("hash_equals", ENDPOINT)
        self.assertIn("$pdo->prepare", ENDPOINT)
        self.assertIn("$statement->execute", ENDPOINT)

    def test_endpoint_rejects_unknown_fields_and_upserts_idempotently(self) -> None:
        self.assertIn("array_diff(array_keys($payload), $allowedKeys)", ENDPOINT)
        self.assertIn("ON DUPLICATE KEY UPDATE", ENDPOINT)
        self.assertIn("session_id VARCHAR(64) PRIMARY KEY", SCHEMA)

    def test_endpoint_contract_excludes_local_scan_evidence(self) -> None:
        for forbidden in ("raw_bgr", "raw_hsv", "image_path", "output_dir", "calibration"):
            self.assertNotIn(forbidden, ENDPOINT)

    def test_dashboard_contains_required_statistics(self) -> None:
        for label in (
            "Total attempts", "Completed solves", "Success rate", "Average moves",
            "Average solve time", "Recent sessions", "Recent errors",
        ):
            self.assertIn(label, DASHBOARD)

    def test_dashboard_deletion_uses_server_key_csrf_and_prepared_sql(self) -> None:
        self.assertIn("hash_equals($configuredKey, DASHBOARD_API_KEY)", DASHBOARD)
        self.assertNotIn('name="api_key"', DASHBOARD)
        self.assertNotIn("Enable removal", DASHBOARD)
        self.assertIn("hash_equals($_SESSION['csrf_token'], $csrf)", DASHBOARD)
        self.assertIn("if (!$canRemove)", DASHBOARD)
        self.assertIn("DELETE FROM solve_runs WHERE session_id = :session_id", DASHBOARD)
        self.assertIn("$statement->execute(['session_id' => $sessionId])", DASHBOARD)
        self.assertIn('name="session_id"', DASHBOARD)
        self.assertIn('name="action" value="delete"', DASHBOARD)
        self.assertIn("303", DASHBOARD)


if __name__ == "__main__":
    unittest.main()
