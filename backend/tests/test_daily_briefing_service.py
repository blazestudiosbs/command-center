import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from services import agent_permission_service, daily_briefing_service
from storage import connection, initialize_storage


class DailyBriefingServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"VERA_DATABASE_PATH": os.path.join(self.temp_dir.name, "vera.db")}, clear=False)
        self.environment.start()
        initialize_storage()
        with connection() as conn:
            conn.execute(
                "INSERT INTO users (id,username,password_hash,role,active,created_utc,updated_utc) VALUES ('owner','bruce','test','owner',1,'2026-08-24T00:00:00Z','2026-08-24T00:00:00Z')"
            )

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_defaults_are_safe_and_disabled(self):
        settings = daily_briefing_service.get_settings("owner")
        self.assertFalse(settings["enabled"])
        self.assertEqual(settings["delivery_time"], "07:00")
        self.assertTrue(agent_permission_service.is_allowed("owner", "daily_briefing", "generate"))
        self.assertFalse(agent_permission_service.is_allowed("owner", "daily_briefing", "scheduled_delivery"))

    def test_generate_is_local_and_read_only(self):
        with patch.object(daily_briefing_service, "_calendar_section", return_value={"status": "ready", "items": []}), patch.object(daily_briefing_service, "_gmail_section", return_value={"status": "ready", "items": []}), patch.object(daily_briefing_service.infrastructure_service, "get_status", return_value={"health": {"issues": []}}), patch.object(daily_briefing_service.service_monitoring_service, "get_status", return_value={"summary": {"healthy": 3, "total": 3}}), patch.object(daily_briefing_service.backup_service, "get_status", return_value={"last_backup": {"status": "completed", "verified": True}}), patch.object(daily_briefing_service.release_service, "list_releases", return_value=[]), patch.object(daily_briefing_service.calendar_service, "pending_changes", return_value=[]):
            result = daily_briefing_service.generate("owner")
        self.assertFalse(result["cloud_processing"])
        self.assertTrue(result["read_only"])
        self.assertIn("3/3 services healthy", daily_briefing_service.format_message(result))

    def test_scheduled_delivery_attempts_only_once_per_day(self):
        settings = daily_briefing_service.get_settings("owner")
        editable = {key: settings[key] for key in ("enabled", "delivery_time", "include_calendar", "include_gmail", "include_infrastructure", "include_backups", "include_approvals")}
        daily_briefing_service.set_settings("owner", **{**editable, "enabled": True, "delivery_time": "07:00"})
        agent_permission_service.set_permission(user_id="owner", agent_id="daily_briefing", capability="scheduled_delivery", enabled=True)
        now = datetime(2026, 8, 24, 7, 1, tzinfo=ZoneInfo("America/Detroit"))
        with patch.object(daily_briefing_service, "generate", return_value={"sections": {}, "timezone": "America/Detroit", "cloud_processing": False, "read_only": True}), patch.object(daily_briefing_service.discord_alert_service, "send", return_value={"sent": False}):
            first = daily_briefing_service.run_if_due("owner", now=now)
            second = daily_briefing_service.run_if_due("owner", now=now)
        self.assertEqual(first["status"], "failed")
        self.assertEqual(second["status"], "skipped")
        with connection() as conn:
            attempts = conn.execute("SELECT COUNT(*) FROM daily_briefing_runs").fetchone()[0]
        self.assertEqual(attempts, 1)


if __name__ == "__main__":
    unittest.main()
