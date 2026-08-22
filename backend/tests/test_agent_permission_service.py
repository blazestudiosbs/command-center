import os
import tempfile
import unittest
from unittest.mock import patch

from services import agent_permission_service, auth_service
from storage import initialize_storage


class AgentPermissionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {
                "VERA_DATABASE_PATH": os.path.join(self.temp_dir.name, "vera.db"),
                "VERA_ADMIN_PASSWORD_HASH": auth_service.hash_password("correct horse battery staple"),
            },
        )
        self.environment.start()
        initialize_storage()
        auth_service.sync_owner()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_defaults_preserve_existing_agents_and_lock_risky_capabilities(self):
        agents = agent_permission_service.list_agents("owner")
        gmail = next(agent for agent in agents if agent["id"] == "gmail")
        monitor = next(agent for agent in agents if agent["id"] == "service_monitor")
        self.assertTrue(gmail["enabled"])
        self.assertFalse(next(item for item in gmail["capabilities"] if item["id"] == "read_inbox")["enabled"])
        self.assertFalse(next(item for item in gmail["capabilities"] if item["id"] == "send")["available"])
        self.assertTrue(next(item for item in monitor["capabilities"] if item["id"] == "background_checks")["enabled"])

    def test_master_toggle_blocks_agent_capabilities(self):
        agent_permission_service.set_permission(
            user_id="owner", agent_id="service_monitor", capability="enabled", enabled=False
        )
        self.assertFalse(agent_permission_service.is_allowed("owner", "service_monitor", "manual_checks"))
        with self.assertRaises(agent_permission_service.AgentPermissionDeniedError):
            agent_permission_service.require("owner", "service_monitor", "manual_checks")

    def test_capability_toggle_is_persisted(self):
        agent_permission_service.set_permission(
            user_id="owner", agent_id="gmail", capability="read_inbox", enabled=True
        )
        self.assertTrue(agent_permission_service.is_allowed("owner", "gmail", "read_inbox"))

    def test_locked_capability_cannot_be_enabled(self):
        with self.assertRaisesRegex(ValueError, "locked off"):
            agent_permission_service.set_permission(
                user_id="owner", agent_id="gmail", capability="send", enabled=True
            )


if __name__ == "__main__":
    unittest.main()
