import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services import (
    agent_permission_service,
    auth_service,
    gmail_cloud_learning_service,
)
from storage import connection, initialize_storage


class GmailCloudLearningServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {
                "VERA_DATABASE_PATH": os.path.join(self.temp_dir.name, "vera.db"),
                "VERA_ADMIN_PASSWORD_HASH": auth_service.hash_password("correct horse battery staple"),
            },
            clear=False,
        )
        self.environment.start()
        initialize_storage()
        auth_service.sync_owner()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def _enable(self):
        agent_permission_service.set_permission(
            user_id="owner", agent_id="gmail", capability="cloud_processing", enabled=True
        )
        with connection() as conn:
            conn.execute("UPDATE cloud_routing_state SET enabled = 1 WHERE id = 'global'")
        gmail_cloud_learning_service.set_enabled("owner", True)

    def test_cannot_enable_without_cloud_processing_permission(self):
        with self.assertRaises(agent_permission_service.AgentPermissionDeniedError):
            gmail_cloud_learning_service.set_enabled("owner", True)

    @patch("services.gmail_cloud_learning_service.cloud_response_service.run_guarded")
    @patch("services.gmail_cloud_learning_service._candidate_messages")
    def test_review_sends_only_sender_and_subject_and_creates_pending_suggestion(self, candidates, guarded):
        self._enable()
        candidates.return_value = [
            {"id": "m1", "sender": "friend@example.com", "subject": "Dinner Sunday"}
        ]
        guarded.return_value = (
            SimpleNamespace(output_text='[{"id":"m1","category":"Personal/Family","reason":"Personal plans"}]'),
            {"actual_cost_usd": 0.001, "estimated_cost_usd": 0.002},
        )

        result = gmail_cloud_learning_service.run_review("owner")

        self.assertEqual(result["suggestions"], 1)
        request = guarded.call_args.kwargs
        self.assertIn("friend@example.com", request["budget_text"])
        self.assertIn("Dinner Sunday", request["budget_text"])
        self.assertNotIn("body", request["input_data"].lower())
        suggestion = gmail_cloud_learning_service.list_suggestions("owner")[0]
        self.assertEqual(suggestion["status"], "pending")

    def test_approval_turns_suggestion_into_local_sender_rule(self):
        now = "2026-08-22T00:00:00Z"
        with connection() as conn:
            conn.execute(
                "INSERT INTO gmail_cloud_review_batches (id,user_id,status,message_count,estimated_cost_usd,actual_cost_usd,created_utc) VALUES ('b1','owner','completed',1,0.001,0.001,?)",
                (now,),
            )
            conn.execute(
                "INSERT INTO gmail_cloud_suggestions (id,batch_id,user_id,sender,suggested_category,reason,created_utc) VALUES ('s1','b1','owner','friend@example.com','Personal/Family','Personal sender',?)",
                (now,),
            )

        result = gmail_cloud_learning_service.review_suggestion("owner", "s1", True)

        self.assertEqual(result["status"], "approved")
        with connection() as conn:
            rule = conn.execute(
                "SELECT category, approved FROM gmail_classification_rules WHERE user_id = 'owner' AND match_value = 'friend@example.com'"
            ).fetchone()
        self.assertEqual(rule["category"], "Personal/Family")
        self.assertTrue(rule["approved"])

    def test_monthly_cap_blocks_before_cloud_call(self):
        self._enable()
        with connection() as conn:
            conn.execute(
                "INSERT INTO gmail_cloud_review_batches (id,user_id,status,message_count,estimated_cost_usd,actual_cost_usd,created_utc) VALUES ('b1','owner','completed',1,0.25,0.25,strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
            )
        with self.assertRaisesRegex(RuntimeError, "monthly Gmail learning cap"):
            gmail_cloud_learning_service.run_review("owner")


if __name__ == "__main__":
    unittest.main()
