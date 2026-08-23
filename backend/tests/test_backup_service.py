import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import auth_service, backup_service
from storage import initialize_storage


class BackupServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "vera.db"
        self.environment = patch.dict(os.environ, {
            "VERA_DATABASE_PATH": str(self.database),
            "VERA_ADMIN_PASSWORD_HASH": auth_service.hash_password("correct horse battery staple"),
        }, clear=False)
        self.environment.start()
        initialize_storage()
        auth_service.sync_owner()

    def tearDown(self):
        self.environment.stop()
        self.temporary.cleanup()

    def test_defaults_are_safe_and_restore_is_not_exposed(self):
        status = backup_service.get_status()
        self.assertTrue(status["settings"]["enabled"])
        self.assertEqual(status["settings"]["daily_retention"], 14)
        self.assertEqual(status["settings"]["weekly_retention"], 8)
        self.assertEqual(status["last_backup"]["status"], "not_installed")

    def test_reads_verified_report(self):
        report = {"status": "completed", "verified": True, "secrets_included": False}
        (self.database.parent / "backup-agent-status.json").write_text(json.dumps(report))
        status = backup_service.get_status()
        self.assertTrue(status["installed"])
        self.assertTrue(status["last_backup"]["verified"])
        self.assertFalse(status["last_backup"]["secrets_included"])


if __name__ == "__main__":
    unittest.main()
