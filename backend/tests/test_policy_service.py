import os
import tempfile
import unittest
from unittest.mock import patch

from services import audit_service, auth_service, policy_service, task_service
from storage import initialize_storage


class PolicyServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {
                "VERA_DATABASE_PATH": os.path.join(self.temp_dir.name, "vera-test.db"),
                "VERA_ADMIN_USERNAME": "bruce",
                "VERA_ADMIN_PASSWORD_HASH": auth_service.hash_password(
                    "correct horse battery staple"
                ),
                "TASK_STORE_PATH": os.path.join(self.temp_dir.name, "tasks.json"),
                "TASK_RUN_DIR": os.path.join(self.temp_dir.name, "task-runs"),
            },
            clear=False,
        )
        self.environment.start()
        initialize_storage()
        auth_service.sync_owner()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_owner_development_permission_is_explicit(self):
        decision = policy_service.evaluate(
            user_id="owner", domain="development", capability="agent_execute"
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.permission_id, "owner-development-agent-execute")

    def test_pause_and_emergency_stop_block_agents_but_keep_read_access(self):
        initial = policy_service.get_control_state()
        paused = policy_service.set_control_mode(
            mode="paused",
            actor_user_id="owner",
            reason="Test pause",
            expected_version=initial["version"],
        )
        self.assertFalse(
            policy_service.evaluate(
                user_id="owner", domain="development", capability="agent_execute"
            ).allowed
        )
        self.assertTrue(
            policy_service.evaluate(
                user_id="owner", domain="vera", capability="conversation"
            ).allowed
        )

        stopped = policy_service.set_control_mode(
            mode="emergency_stop",
            actor_user_id="owner",
            reason="Test stop",
            expected_version=paused["version"],
        )
        self.assertEqual(stopped["mode"], "emergency_stop")
        self.assertFalse(
            policy_service.evaluate(
                user_id="owner", domain="email", capability="external_side_effect"
            ).allowed
        )
        self.assertFalse(
            policy_service.evaluate(
                user_id="owner", domain="home", capability="manual_write"
            ).allowed
        )

        initialize_storage()
        self.assertEqual(policy_service.get_control_state()["mode"], "emergency_stop")

    def test_stale_control_version_is_rejected(self):
        current = policy_service.get_control_state()
        policy_service.set_control_mode(
            mode="paused",
            actor_user_id="owner",
            reason="First change",
            expected_version=current["version"],
        )
        with self.assertRaises(policy_service.ControlVersionConflictError):
            policy_service.set_control_mode(
                mode="active",
                actor_user_id="owner",
                reason="Stale change",
                expected_version=current["version"],
            )

    def test_direct_task_service_call_cannot_bypass_pause(self):
        task = task_service.create_task(
            {"title": "Policy test", "goal": "Verify the executor gate"}
        )
        policy_service.set_control_mode(
            mode="paused", actor_user_id="owner", reason="Test direct bypass"
        )
        with self.assertRaises(policy_service.PolicyDeniedError):
            task_service.run_task_command(task["id"], "git_status_short")

        denial = audit_service.list_events()[0]
        self.assertEqual(denial["outcome"], "denied")
        self.assertEqual(denial["resource_id"], task["id"])


if __name__ == "__main__":
    unittest.main()
