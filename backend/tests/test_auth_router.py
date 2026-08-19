import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.auth import router
from services.auth_service import hash_password
from storage import initialize_storage


class AuthRouterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.password = "correct horse battery staple"
        self.environment = patch.dict(
            os.environ,
            {
                "VERA_DATABASE_PATH": os.path.join(self.temp_dir.name, "vera-test.db"),
                "VERA_ADMIN_USERNAME": "bruce",
                "VERA_ADMIN_PASSWORD_HASH": hash_password(self.password),
                "VERA_COOKIE_SECURE": "false",
            },
            clear=False,
        )
        self.environment.start()
        initialize_storage()
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_login_me_and_logout(self):
        login = self.client.post(
            "/api/auth/login",
            json={"username": "bruce", "password": self.password},
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["user"]["role"], "owner")
        self.assertIn("HttpOnly", login.headers["set-cookie"])
        csrf_token = login.json()["csrf_token"]

        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"]["username"], "bruce")

        rejected_logout = self.client.post("/api/auth/logout")
        self.assertEqual(rejected_logout.status_code, 403)

        logout = self.client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": csrf_token},
        )
        self.assertEqual(logout.status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_invalid_credentials_are_rejected(self):
        response = self.client.post(
            "/api/auth/login",
            json={"username": "bruce", "password": "incorrect password"},
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
