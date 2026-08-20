import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from services import audit_service, auth_service, conversation_service, discord_binding_service
from storage import connection, initialize_storage


class VeraStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "vera-test.db")
        self.environment = patch.dict(
            os.environ,
            {
                "VERA_DATABASE_PATH": self.database_path,
                "VERA_ADMIN_USERNAME": "bruce",
                "VERA_ADMIN_PASSWORD_HASH": auth_service.hash_password(
                    "correct horse battery staple"
                ),
            },
            clear=False,
        )
        self.environment.start()
        initialize_storage()
        self.assertTrue(auth_service.sync_owner())

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_all_migrations_are_recorded_and_repeatable(self):
        initialize_storage()
        with connection() as conn:
            migrations = conn.execute(
                "SELECT version, name FROM schema_migrations ORDER BY version"
            ).fetchall()
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        self.assertEqual(
            [(row[0], row[1]) for row in migrations],
            [
                (1, "auth"),
                (2, "vera_core"),
                (3, "discord_gateway"),
                (4, "budget_ledger"),
                (5, "domain_policies"),
                (6, "routing_decisions"),
                (7, "cloud_routing_control"),
            ],
        )
        self.assertTrue(
            {
                "users",
                "sessions",
                "conversations",
                "messages",
                "control_state",
                "permissions",
                "audit_events",
                "conversation_bindings",
                "budget_ledger",
                "domain_policies",
                "routing_decisions",
                "cloud_routing_state",
            }.issubset(tables)
        )

    def test_conversation_and_messages_persist_in_order(self):
        conversation = conversation_service.create_conversation("owner", "First chat")
        first = conversation_service.add_message(
            conversation_id=conversation["id"],
            owner_user_id="owner",
            role="user",
            content="Hello Vera",
            client_message_id="phone-message-1",
        )
        second = conversation_service.add_message(
            conversation_id=conversation["id"],
            owner_user_id="owner",
            role="assistant",
            content="Hello Bruce",
            model="test-model",
        )

        messages = conversation_service.list_messages(conversation["id"], "owner")
        self.assertEqual([message["id"] for message in messages], [first["id"], second["id"]])
        self.assertEqual([message["sequence"] for message in messages], [1, 2])
        self.assertEqual(messages[1]["model"], "test-model")

    def test_duplicate_client_message_is_idempotent(self):
        conversation = conversation_service.create_conversation("owner")
        first = conversation_service.add_message(
            conversation_id=conversation["id"],
            owner_user_id="owner",
            role="user",
            content="Send once",
            client_message_id="stable-client-id",
        )
        retry = conversation_service.add_message(
            conversation_id=conversation["id"],
            owner_user_id="owner",
            role="user",
            content="Send once",
            client_message_id="stable-client-id",
        )
        self.assertEqual(first["id"], retry["id"])
        self.assertEqual(len(conversation_service.list_messages(conversation["id"], "owner")), 1)

    def test_owner_scope_hides_conversations_and_messages(self):
        conversation = conversation_service.create_conversation("owner")
        self.assertIsNone(conversation_service.get_conversation(conversation["id"], "someone-else"))
        with self.assertRaises(conversation_service.ConversationNotFoundError):
            conversation_service.list_messages(conversation["id"], "someone-else")

    def test_audit_events_are_append_only(self):
        event = audit_service.append_event(
            actor_user_id="owner",
            action="conversation.created",
            resource_type="conversation",
            resource_id="example",
            outcome="succeeded",
            details={"source": "test"},
        )
        self.assertEqual(audit_service.list_events()[0]["id"], event["id"])

        with self.assertRaises(sqlite3.IntegrityError):
            with connection() as conn:
                conn.execute(
                    "UPDATE audit_events SET outcome = 'failed' WHERE id = ?",
                    (event["id"],),
                )
        with self.assertRaises(sqlite3.IntegrityError):
            with connection() as conn:
                conn.execute("DELETE FROM audit_events WHERE id = ?", (event["id"],))

    def test_global_control_state_starts_active(self):
        with connection() as conn:
            state = conn.execute(
                "SELECT mode, version FROM control_state WHERE id = 'global'"
            ).fetchone()
        self.assertEqual((state["mode"], state["version"]), ("active", 1))

    def test_discord_channel_binds_to_one_persistent_conversation_and_user(self):
        first = discord_binding_service.get_or_create(
            owner_user_id="owner", guild_id="guild-1", channel_id="channel-1", discord_user_id="user-1"
        )
        again = discord_binding_service.get_or_create(
            owner_user_id="owner", guild_id="guild-1", channel_id="channel-1", discord_user_id="user-1"
        )
        self.assertEqual(first["conversation_id"], again["conversation_id"])
        with self.assertRaises(discord_binding_service.DiscordIdentityDeniedError):
            discord_binding_service.get_or_create(
                owner_user_id="owner", guild_id="guild-1", channel_id="channel-1", discord_user_id="user-2"
            )


class PhaseOneUpgradeTests(unittest.TestCase):
    def test_existing_owner_and_session_survive_migrations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "phase-one.db")
            with sqlite3.connect(path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE users (
                        id TEXT PRIMARY KEY,
                        username TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL,
                        active INTEGER NOT NULL,
                        created_utc TEXT NOT NULL,
                        updated_utc TEXT NOT NULL
                    );
                    CREATE TABLE sessions (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES users(id),
                        token_hash TEXT NOT NULL UNIQUE,
                        csrf_token TEXT NOT NULL,
                        created_utc TEXT NOT NULL,
                        expires_utc TEXT NOT NULL,
                        last_seen_utc TEXT NOT NULL
                    );
                    INSERT INTO users VALUES
                        ('owner', 'bruce', 'existing-hash', 'owner', 1,
                         '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
                    INSERT INTO sessions VALUES
                        ('session-1', 'owner', 'token-hash', 'csrf-token',
                         '2026-01-01T00:00:00Z', '2099-01-01T00:00:00Z',
                         '2026-01-01T00:00:00Z');
                    """
                )

            with patch.dict(os.environ, {"VERA_DATABASE_PATH": path}, clear=False):
                initialize_storage()
                with connection() as conn:
                    owner = conn.execute("SELECT username FROM users WHERE id = 'owner'").fetchone()
                    session = conn.execute("SELECT id FROM sessions WHERE id = 'session-1'").fetchone()
                    conversation_table = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'conversations'"
                    ).fetchone()

            self.assertEqual(owner["username"], "bruce")
            self.assertEqual(session["id"], "session-1")
            self.assertEqual(conversation_table["name"], "conversations")


if __name__ == "__main__":
    unittest.main()
