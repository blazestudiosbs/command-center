import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location("backup_agent", Path(__file__).with_name("agent.py"))
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class BackupAgentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        agent.CONFIG = root / "config"
        agent.CONFIG.mkdir()
        agent.DATABASE = agent.CONFIG / "vera.db"
        agent.STATUS_FILE = agent.CONFIG / "backup-agent-status.json"
        self.destination = root / "backups"
        with sqlite3.connect(agent.DATABASE) as conn:
            conn.execute("CREATE TABLE sample (value TEXT)")
            conn.execute("INSERT INTO sample VALUES ('important data')")
            conn.execute("CREATE TABLE backup_agent_settings (id TEXT PRIMARY KEY, enabled INTEGER, destination TEXT, daily_retention INTEGER, weekly_retention INTEGER)")
            conn.execute("INSERT INTO backup_agent_settings VALUES ('global',1,?,14,8)", (str(self.destination),))

    def tearDown(self):
        self.temporary.cleanup()

    def test_creates_and_verifies_consistent_archive_without_secrets(self):
        (agent.CONFIG / "projects.json").write_text('{"projects": []}')
        (agent.CONFIG / ".env").write_text("SECRET=not-for-backup")
        self.assertEqual(agent.run_backup(), 0)
        report = json.loads(agent.STATUS_FILE.read_text())
        self.assertEqual(report["status"], "completed")
        self.assertTrue(report["verified"])
        manifest = agent.verify_archive(Path(report["archive"]))
        self.assertIn("vera.db", manifest["files"])
        self.assertIn("projects.json", manifest["files"])
        self.assertNotIn(".env", manifest["files"])

    def test_disabled_agent_does_not_create_archive(self):
        with sqlite3.connect(agent.DATABASE) as conn:
            conn.execute("UPDATE backup_agent_settings SET enabled = 0")
        self.assertEqual(agent.run_backup(), 0)
        self.assertEqual(json.loads(agent.STATUS_FILE.read_text())["status"], "disabled")
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
