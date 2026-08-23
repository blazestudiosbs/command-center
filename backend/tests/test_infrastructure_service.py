import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import auth_service, infrastructure_service
from storage import initialize_storage


class InfrastructureServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "vera.db"
        self.environment = patch.dict(os.environ, {
            "VERA_DATABASE_PATH": str(self.db_path),
            "VERA_ADMIN_PASSWORD_HASH": auth_service.hash_password("correct horse battery staple"),
        }, clear=False)
        self.environment.start()
        initialize_storage()
        auth_service.sync_owner()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_safe_recommended_defaults(self):
        settings = infrastructure_service.get_settings()
        self.assertTrue(settings["security_updates_enabled"])
        self.assertTrue(settings["health_checks_enabled"])
        self.assertFalse(settings["automatic_reboot"])
        self.assertEqual(settings["timezone"], "America/Detroit")
        self.assertEqual(settings["schedule"], "Monday 03:00")

    def test_reads_host_agent_report_from_config_directory(self):
        report = {"health": {"status": "healthy", "issues": [], "checked_utc": "now"}, "updates": {"status": "completed", "reboot_performed": False}}
        (self.db_path.parent / "infrastructure-agent-status.json").write_text(json.dumps(report))
        status = infrastructure_service.get_status()
        self.assertTrue(status["installed"])
        self.assertEqual(status["health"]["status"], "healthy")
        self.assertFalse(status["updates"]["reboot_performed"])

    def test_settings_can_disable_agents_but_never_enable_reboot(self):
        settings = infrastructure_service.set_settings(security_updates_enabled=False, health_checks_enabled=False)
        self.assertFalse(settings["security_updates_enabled"])
        self.assertFalse(settings["health_checks_enabled"])
        self.assertFalse(settings["automatic_reboot"])


if __name__ == "__main__":
    unittest.main()
