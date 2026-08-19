import os
import tempfile
import unittest
from unittest.mock import patch

from services import auth_service
from storage import initialize_storage


class AuthServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "vera-test.db")
        self.password = "correct horse battery staple"
        self.password_hash = auth_service.hash_password(self.password)
        self.environment = patch.dict(
            os.environ,
            {
                "VERA_DATABASE_PATH": self.database_path,
                "VERA_ADMIN_USERNAME": "bruce",
                "VERA_ADMIN_PASSWORD_HASH": self.password_hash,
            },
            clear=False,
        )
        self.environment.start()
        initialize_storage()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_password_hash_round_trip(self):
        self.assertTrue(auth_service.verify_password(self.password, self.password_hash))
        self.assertFalse(auth_service.verify_password("incorrect password", self.password_hash))

    def test_password_requires_twelve_characters(self):
        with self.assertRaises(ValueError):
            auth_service.hash_password("too short")

    def test_authenticate_creates_owner_identity(self):
        user = auth_service.authenticate("bruce", self.password)
        self.assertEqual(user, {"id": "owner", "username": "bruce", "role": "owner"})
        self.assertIsNone(auth_service.authenticate("bruce", "incorrect password"))

    def test_session_is_stored_by_hash_and_can_be_revoked(self):
        user = auth_service.authenticate("bruce", self.password)
        session = auth_service.create_session(user["id"])

        resolved = auth_service.get_session(session["token"])
        self.assertEqual(resolved["user_id"], "owner")
        self.assertEqual(resolved["csrf_token"], session["csrf_token"])

        auth_service.delete_session(session["token"])
        self.assertIsNone(auth_service.get_session(session["token"]))


if __name__ == "__main__":
    unittest.main()
