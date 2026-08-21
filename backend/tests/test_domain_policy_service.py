import os
import tempfile
import unittest
from unittest.mock import patch

from services import policy_service
from storage import initialize_storage


class DomainPolicyServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {"VERA_DATABASE_PATH": os.path.join(self.temp_dir.name, "vera-test.db")},
            clear=False,
        )
        self.environment.start()
        initialize_storage()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_expected_domain_defaults_are_seeded(self):
        policies = {policy["domain"]: policy for policy in policy_service.list_domain_policies()}

        self.assertTrue(
            {"general", "home", "family", "development", "security", "conversation"}.issubset(policies)
        )
        self.assertFalse(policies["family"]["cloud_allowed"])
        self.assertTrue(policies["security"]["approval_required"])
        self.assertTrue(policies["conversation"]["cloud_allowed"])
        self.assertEqual(policies["conversation"]["max_request_usd"], 0.02)

    def test_family_cloud_request_fails_closed(self):
        decision = policy_service.evaluate_domain_request(
            domain="family",
            provider="openai",
            model="gpt-4.1-mini",
            estimated_cost_usd=0.001,
        )

        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["effect"], "deny")
        self.assertIn("Cloud models are disabled", decision["reason"])
        self.assertFalse(decision["cloud_call_made"])

    def test_development_cloud_request_requires_approval(self):
        pending = policy_service.evaluate_domain_request(
            domain="development",
            provider="openai",
            model="gpt-4.1-mini",
            estimated_cost_usd=0.01,
        )
        approved = policy_service.evaluate_domain_request(
            domain="development",
            provider="openai",
            model="gpt-4.1-mini",
            estimated_cost_usd=0.01,
            approved=True,
        )

        self.assertEqual(pending["effect"], "approval_required")
        self.assertFalse(pending["allowed"])
        self.assertTrue(approved["allowed"])

    def test_domain_limit_blocks_request_before_global_limit(self):
        decision = policy_service.evaluate_domain_request(
            domain="home",
            provider="openai",
            model="gpt-4.1-mini",
            estimated_cost_usd=0.03,
        )

        self.assertFalse(decision["allowed"])
        self.assertIn("domain's per-request limit", decision["reason"])

    def test_unknown_domain_is_denied(self):
        decision = policy_service.evaluate_domain_request(
            domain="unknown",
            provider="local",
            model="qwen3:4b",
            estimated_cost_usd=0,
        )

        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["effect"], "deny")


if __name__ == "__main__":
    unittest.main()
