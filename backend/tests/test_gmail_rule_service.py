import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from services import agent_permission_service, auth_service, gmail_rule_service
from storage import connection, initialize_storage


class GmailRuleServiceTests(unittest.TestCase):
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

    def test_parser_requires_explicit_permanent_delete_and_exact_email(self):
        request = gmail_rule_service.parse_rule_request(
            "Anything new or old from store-news@amazon.com can be permanently deleted."
        )
        self.assertEqual(request["sender"], "store-news@amazon.com")
        self.assertIsNone(gmail_rule_service.parse_rule_request("Delete Amazon newsletters"))

    @patch("services.gmail_rule_service._count_matches", return_value=12)
    @patch("services.gmail_rule_service.gmail_service.get_status", return_value={"connected": True})
    def test_proposal_is_pending_after_validation(self, _status, _count):
        agent_permission_service.set_permission(
            user_id="owner", agent_id="gmail", capability="search", enabled=True
        )
        rule = gmail_rule_service.propose("owner", "store-news@amazon.com", source="discord")
        self.assertEqual(rule["status"], "pending")
        self.assertEqual(rule["validation_match_count"], 12)

    def test_approval_requires_separate_delete_permission(self):
        with connection() as conn:
            conn.execute(
                "INSERT INTO gmail_automation_rules (id,user_id,sender,action,status,validation_match_count,validation_note,created_source,created_utc) VALUES ('r1','owner','store-news@amazon.com','permanent_delete','pending',0,'validated','test','2026-08-22T00:00:00Z')"
            )
        with self.assertRaises(agent_permission_service.AgentPermissionDeniedError):
            gmail_rule_service.decide("owner", "r1", True)

    @patch("services.gmail_rule_service.gmail_service._message_metadata")
    @patch("services.gmail_rule_service.gmail_service._access_token", return_value="token")
    @patch("services.gmail_rule_service.gmail_service.get_status", return_value={"permanent_delete_authorized": True})
    @patch("services.gmail_rule_service.requests.delete")
    @patch("services.gmail_rule_service.requests.get")
    def test_executor_rechecks_exact_sender_before_permanent_delete(self, get, delete, _status, _token, metadata):
        agent_permission_service.set_permission(
            user_id="owner", agent_id="gmail", capability="permanent_delete", enabled=True
        )
        with connection() as conn:
            conn.execute(
                "INSERT INTO gmail_automation_rules (id,user_id,sender,action,status,validation_match_count,validation_note,created_source,created_utc) VALUES ('r1','owner','store-news@amazon.com','permanent_delete','active',0,'validated','test','2026-08-22T00:00:00Z')"
            )
        listing = Mock()
        listing.json.return_value = {"messages": [{"id": "exact"}, {"id": "near-match"}]}
        listing.raise_for_status.return_value = None
        get.return_value = listing
        metadata.side_effect = [
            {"sender": "Amazon <store-news@amazon.com>", "subject": "Sale"},
            {"sender": "Imposter <store-news@amazon.example>", "subject": "Sale"},
        ]
        deleted = Mock()
        deleted.raise_for_status.return_value = None
        delete.return_value = deleted

        result = gmail_rule_service.run_active_rules("owner")

        self.assertEqual(result["deleted"], 1)
        self.assertEqual(delete.call_count, 1)
        self.assertTrue(delete.call_args.args[0].endswith("/exact"))


if __name__ == "__main__":
    unittest.main()
