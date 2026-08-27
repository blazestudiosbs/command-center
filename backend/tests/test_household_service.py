import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import auth_service, household_service
from storage import connection, initialize_storage


class HouseholdServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        secret_path = Path(self.temp_dir.name) / "identity-key"
        secret_path.write_bytes(b"h" * 32)
        self.environment = patch.dict(os.environ, {
            "VERA_DATABASE_PATH": str(Path(self.temp_dir.name) / "vera.db"),
            "VERA_ADMIN_PASSWORD_HASH": auth_service.hash_password("correct horse battery staple"),
            "VERA_IDENTITY_HASH_KEY_FILE": str(secret_path),
        }, clear=False)
        self.environment.start()
        initialize_storage()
        auth_service.sync_owner()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_owner_member_is_seeded_lazily(self):
        members = household_service.list_members()
        self.assertEqual([(item["id"], item["user_id"], item["role"]) for item in members], [("owner", "owner", "owner")])

    def test_voice_subject_is_hashed_and_resolves_to_owner(self):
        household_service.link_voice_identity(member_id="owner", provider="amazon_alexa", subject_id="raw-amazon-subject")
        identity = household_service.resolve_voice_identity(provider="amazon_alexa", subject_id="raw-amazon-subject")
        self.assertEqual(identity["member_id"], "owner")
        with connection() as conn:
            stored = conn.execute("SELECT subject_hash FROM household_voice_identities").fetchone()["subject_hash"]
        self.assertNotEqual(stored, "raw-amazon-subject")
        self.assertEqual(len(stored), 64)

    def test_member_without_private_account_cannot_be_linked(self):
        household_service.ensure_owner_member()
        with connection() as conn:
            conn.execute("INSERT INTO household_members (id,user_id,display_name,role,status,created_utc,updated_utc) VALUES ('guest',NULL,'Guest','guest','active','now','now')")
        with self.assertRaises(ValueError):
            household_service.link_voice_identity(member_id="guest", provider="amazon_alexa", subject_id="guest-subject")


if __name__ == "__main__":
    unittest.main()
