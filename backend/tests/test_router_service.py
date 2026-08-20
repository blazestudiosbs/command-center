import os
import tempfile
import unittest
from unittest.mock import patch

from services import budget_service, router_service
from storage import initialize_storage


class RouterServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {
                "VERA_DATABASE_PATH": os.path.join(self.temp_dir.name, "vera-test.db"),
                "VERA_LOCAL_MODEL": "test-local",
                "OPENAI_MODEL": "gpt-4.1-mini",
            },
            clear=False,
        )
        self.environment.start()
        initialize_storage()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_local_model_is_selected_first(self):
        result = router_service.simulate(
            domain="general",
            prompt="What is on my list?",
            max_output_tokens=100,
            local_confidence=0.9,
        )

        self.assertEqual(result["decision"], "local")
        self.assertEqual(result["selected_provider"], "local")
        self.assertFalse(result["execution_performed"])
        self.assertFalse(result["cloud_call_made"])
        self.assertEqual(budget_service.list_ledger(), [])

    def test_cloud_routing_defaults_off_and_persists_explicit_change(self):
        initial = router_service.get_cloud_routing_state()
        self.assertFalse(initial["enabled"])
        self.assertFalse(initial["effective_enabled"])

        enabled = router_service.set_cloud_routing(
            enabled=True,
            actor_user_id=None,
            reason="Test enable",
            expected_version=initial["version"],
        )
        self.assertTrue(enabled["enabled"])
        self.assertTrue(enabled["effective_enabled"])
        self.assertTrue(router_service.get_cloud_routing_state()["enabled"])

        with self.assertRaises(router_service.CloudRoutingVersionConflictError):
            router_service.set_cloud_routing(
                enabled=False,
                actor_user_id=None,
                reason="Stale disable",
                expected_version=initial["version"],
            )

    def test_low_confidence_general_request_would_escalate(self):
        result = router_service.simulate(
            domain="general",
            prompt="Plan a complicated project",
            max_output_tokens=400,
            local_confidence=0.2,
        )

        self.assertEqual(result["decision"], "would_escalate")
        self.assertEqual(result["selected_provider"], "openai")
        self.assertFalse(result["cloud_call_made"])
        self.assertEqual(len(budget_service.list_ledger()), 1)

    def test_development_escalation_waits_for_approval(self):
        result = router_service.simulate(
            domain="development",
            prompt="Review this deployment",
            max_output_tokens=400,
            local_confidence=0.2,
        )

        self.assertEqual(result["decision"], "approval_required")
        self.assertIsNone(result["selected_provider"])

    def test_family_cloud_denial_falls_back_to_available_local_model(self):
        result = router_service.simulate(
            domain="family",
            prompt="Summarize private family notes",
            max_output_tokens=400,
            local_available=True,
            local_confidence=0.2,
        )

        self.assertEqual(result["decision"], "local_fallback")
        self.assertEqual(result["selected_provider"], "local")
        self.assertIn("Cloud models are disabled", result["reason"])

    def test_no_local_model_and_denied_cloud_route_is_blocked(self):
        result = router_service.simulate(
            domain="family",
            prompt="Summarize private family notes",
            max_output_tokens=400,
            local_available=False,
            local_confidence=0,
        )

        self.assertEqual(result["decision"], "blocked")
        self.assertIsNone(result["selected_provider"])

    def test_unknown_domain_cannot_bypass_policy_with_local_route(self):
        result = router_service.simulate(
            domain="unknown",
            prompt="Do something",
            max_output_tokens=100,
            local_available=True,
            local_confidence=1,
        )

        self.assertEqual(result["decision"], "blocked")
        self.assertIsNone(result["selected_provider"])
        self.assertIn("No policy exists", result["reason"])


if __name__ == "__main__":
    unittest.main()
