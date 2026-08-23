import os
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

from services import auth_service, gmail_service
from storage import connection, initialize_storage


class GmailServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {
                "VERA_DATABASE_PATH": os.path.join(self.temp_dir.name, "vera.db"),
                "VERA_ADMIN_PASSWORD_HASH": auth_service.hash_password("correct horse battery staple"),
                "GMAIL_CLIENT_ID": "client-id.apps.googleusercontent.com",
                "GMAIL_CLIENT_SECRET": "client-secret",
                "GMAIL_OAUTH_REDIRECT_URI": "https://command-center.example.ts.net/api/gmail/oauth/callback",
                "VERA_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
            },
            clear=False,
        )
        self.environment.start()
        initialize_storage()
        auth_service.sync_owner()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_status_is_safe_and_ready_without_connection(self):
        status = gmail_service.get_status("owner")
        self.assertTrue(status["configured"])
        self.assertFalse(status["connected"])
        self.assertEqual(status["access"], "read_only")
        self.assertFalse(status["can_send"])
        self.assertNotIn("client-secret", str(status))

    def test_authorization_uses_modify_scope_and_one_time_state(self):
        authorization_url = gmail_service.authorization_url("owner")
        query = parse_qs(urlparse(authorization_url).query)
        self.assertEqual(query["scope"], [gmail_service.GMAIL_MODIFY_SCOPE])
        self.assertEqual(query["access_type"], ["offline"])
        self.assertEqual(query["redirect_uri"], [os.environ["GMAIL_OAUTH_REDIRECT_URI"]])
        with connection() as conn:
            row = conn.execute("SELECT * FROM gmail_oauth_states WHERE state = ?", (query["state"][0],)).fetchone()
        self.assertEqual(row["user_id"], "owner")

    def test_permanent_delete_authorization_is_explicit_and_separate(self):
        authorization_url = gmail_service.authorization_url("owner", permanent_delete=True)
        query = parse_qs(urlparse(authorization_url).query)
        self.assertEqual(query["scope"], [gmail_service.GMAIL_FULL_SCOPE])

    @patch("services.gmail_service.requests.get")
    @patch("services.gmail_service.requests.post")
    def test_callback_encrypts_refresh_token_and_connects(self, post, get):
        token_response = Mock()
        token_response.json.return_value = {
            "access_token": "short-lived-access",
            "refresh_token": "private-refresh-token",
            "scope": gmail_service.GMAIL_READONLY_SCOPE,
        }
        token_response.raise_for_status.return_value = None
        post.return_value = token_response
        profile_response = Mock()
        profile_response.json.return_value = {"emailAddress": "bruce@example.com"}
        profile_response.raise_for_status.return_value = None
        get.return_value = profile_response
        state = parse_qs(urlparse(gmail_service.authorization_url("owner")).query)["state"][0]

        result = gmail_service.complete_authorization(state, "one-time-code")

        self.assertTrue(result["connected"])
        self.assertEqual(result["email_address"], "bruce@example.com")
        with connection() as conn:
            row = conn.execute("SELECT encrypted_refresh_token FROM gmail_connections").fetchone()
            state_row = conn.execute("SELECT state FROM gmail_oauth_states WHERE state = ?", (state,)).fetchone()
        self.assertNotIn("private-refresh-token", row["encrypted_refresh_token"])
        self.assertIsNone(state_row)

    def test_invalid_state_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "invalid or expired"):
            gmail_service.complete_authorization("unknown-state", "code")

    @patch("services.gmail_service.requests.get")
    @patch("services.gmail_service.requests.post")
    def test_organizer_preview_is_local_and_does_not_modify_gmail(self, post, get):
        encrypted = gmail_service._fernet().encrypt(b"refresh-token").decode("ascii")
        with connection() as conn:
            conn.execute(
                """
                INSERT INTO gmail_connections
                    (user_id, email_address, encrypted_refresh_token, scopes_json, connected_utc, updated_utc)
                VALUES ('owner', 'bruce@example.com', ?, ?, '2026-08-22T00:00:00Z', '2026-08-22T00:00:00Z')
                """,
                (encrypted, '["https://www.googleapis.com/auth/gmail.readonly"]'),
            )
        token_response = Mock()
        token_response.json.return_value = {"access_token": "access-token"}
        token_response.raise_for_status.return_value = None
        post.return_value = token_response
        list_response = Mock()
        list_response.json.return_value = {"messages": [{"id": "message-1"}]}
        list_response.raise_for_status.return_value = None
        detail_response = Mock()
        detail_response.json.return_value = {
            "payload": {
                "headers": [
                    {"name": "From", "value": "Amazon Orders <orders@amazon.com>"},
                    {"name": "Subject", "value": "Your order has shipped"},
                    {"name": "Date", "value": "Sat, 22 Aug 2026 10:00:00 -0400"},
                ]
            }
        }
        detail_response.raise_for_status.return_value = None
        get.side_effect = [list_response, detail_response]

        preview = gmail_service.organizer_preview("owner", limit=10)

        self.assertEqual(preview["mode"], "simulation")
        self.assertFalse(preview["cloud_processing"])
        self.assertEqual(preview["messages"][0]["category"], "Shopping/Shipping")
        self.assertEqual(preview["messages"][0]["confidence"], "high")
        self.assertEqual(
            preview["messages"][0]["labels"],
            ["Vera/Shopping/Shipping", "Vera/Senders/Amazon Orders"],
        )
        self.assertTrue(preview["messages"][0]["remove_from_inbox"])
        self.assertEqual(post.call_count, 1)
        self.assertEqual(get.call_count, 2)

    def test_sender_label_is_sanitized(self):
        self.assertEqual(gmail_service._safe_label("Bad/Label\nName", "Unknown"), "Bad-Label-Name")

    def test_uncertain_message_is_sent_to_needs_review(self):
        self.assertEqual(
            gmail_service._classification("A Person <person@example.com>", "Hello there"),
            ("Needs Review", "low"),
        )

    def test_detailed_categories_are_prioritized(self):
        self.assertEqual(
            gmail_service._classification("My Bank <alerts@bank.example>", "Your account statement is ready"),
            ("Financial/Banking", "high"),
        )
        self.assertEqual(
            gmail_service._classification("Airline <travel@example.com>", "Your boarding pass"),
            ("Travel/Flights", "high"),
        )

    def test_user_correction_becomes_a_zero_cost_sender_rule(self):
        rule = gmail_service.learn_sender_rule(
            "owner", "Friendly Person <friend@example.com>", "Personal/Family"
        )

        self.assertEqual(rule["match_value"], "friend@example.com")
        self.assertTrue(rule["approved"])
        self.assertEqual(
            gmail_service._classification(
                "Friendly Person <friend@example.com>", "An unrelated subject", "owner"
            ),
            ("Personal/Family", "learned"),
        )
        learning = gmail_service.get_learning_status("owner")
        self.assertEqual(learning["learned_rule_count"], 1)
        self.assertFalse(learning["cloud_review_enabled"])
        self.assertEqual(learning["monthly_budget_usd"], 0.25)
        self.assertEqual(learning["weekly_message_limit"], 20)
        self.assertFalse(learning["include_message_bodies"])

    def test_sender_rule_rejects_unknown_category(self):
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            gmail_service.learn_sender_rule(
                "owner", "sender@example.com", "Something/Invented"
            )

    def test_organizer_cannot_enable_without_modify_authorization(self):
        encrypted = gmail_service._fernet().encrypt(b"refresh-token").decode("ascii")
        with connection() as conn:
            conn.execute(
                """
                INSERT INTO gmail_connections
                    (user_id, email_address, encrypted_refresh_token, scopes_json, connected_utc, updated_utc)
                VALUES ('owner', 'bruce@example.com', ?, ?, '2026-08-22T00:00:00Z', '2026-08-22T00:00:00Z')
                """,
                (encrypted, f'["{gmail_service.GMAIL_READONLY_SCOPE}"]'),
            )
        with self.assertRaisesRegex(RuntimeError, "Reconnect"):
            gmail_service.set_organizer_enabled("owner", True)

    def test_organizer_settings_enable_after_modify_authorization(self):
        encrypted = gmail_service._fernet().encrypt(b"refresh-token").decode("ascii")
        with connection() as conn:
            conn.execute(
                """
                INSERT INTO gmail_connections
                    (user_id, email_address, encrypted_refresh_token, scopes_json, connected_utc, updated_utc)
                VALUES ('owner', 'bruce@example.com', ?, ?, '2026-08-22T00:00:00Z', '2026-08-22T00:00:00Z')
                """,
                (encrypted, f'["{gmail_service.GMAIL_MODIFY_SCOPE}"]'),
            )
        settings = gmail_service.set_organizer_enabled("owner", True)
        self.assertTrue(settings["enabled"])
        self.assertEqual(settings["filing_mode"], "apply_labels_then_remove_inbox")

    @patch("services.gmail_service.requests.get")
    @patch("services.gmail_service.requests.post")
    def test_live_organizer_labels_before_removing_inbox(self, post, get):
        encrypted = gmail_service._fernet().encrypt(b"refresh-token").decode("ascii")
        with connection() as conn:
            conn.execute(
                """
                INSERT INTO gmail_connections
                    (user_id, email_address, encrypted_refresh_token, scopes_json, connected_utc, updated_utc)
                VALUES ('owner', 'bruce@example.com', ?, ?, '2026-08-22T00:00:00Z', '2026-08-22T00:00:00Z')
                """,
                (encrypted, f'["{gmail_service.GMAIL_MODIFY_SCOPE}"]'),
            )
        gmail_service.set_organizer_enabled("owner", True)
        token = Mock(); token.json.return_value = {"access_token": "access"}; token.raise_for_status.return_value = None
        label_one = Mock(); label_one.json.return_value = {"id": "label-category"}; label_one.raise_for_status.return_value = None
        label_two = Mock(); label_two.json.return_value = {"id": "label-sender"}; label_two.raise_for_status.return_value = None
        modified = Mock(); modified.raise_for_status.return_value = None
        post.side_effect = [token, label_one, label_two, modified]
        listing = Mock(); listing.json.return_value = {"messages": [{"id": "m1"}]}; listing.raise_for_status.return_value = None
        metadata = Mock(); metadata.json.return_value = {"payload": {"headers": [
            {"name": "From", "value": "Amazon <orders@amazon.com>"},
            {"name": "Subject", "value": "Your order has shipped"},
        ]}}; metadata.raise_for_status.return_value = None
        labels = Mock(); labels.json.return_value = {"labels": []}; labels.raise_for_status.return_value = None
        get.side_effect = [listing, metadata, labels]

        result = gmail_service.run_organizer("owner", include_existing=True)

        self.assertEqual(result, {"status": "completed", "processed": 1, "failed": 0})
        modify_call = post.call_args_list[-1]
        self.assertTrue(modify_call.args[0].endswith("/messages/m1/modify"))
        self.assertEqual(modify_call.kwargs["json"]["removeLabelIds"], ["INBOX"])
        self.assertEqual(modify_call.kwargs["json"]["addLabelIds"], ["label-category", "label-sender"])


if __name__ == "__main__":
    unittest.main()
