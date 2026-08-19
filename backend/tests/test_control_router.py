import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.auth import router as auth_router
from routers.control import router as control_router
from services import auth_service
from storage import initialize_storage


class ControlRouterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.password = "correct horse battery staple"
        self.environment = patch.dict(
            os.environ,
            {
                "VERA_DATABASE_PATH": os.path.join(self.temp_dir.name, "vera-test.db"),
                "VERA_ADMIN_USERNAME": "bruce",
                "VERA_ADMIN_PASSWORD_HASH": auth_service.hash_password(self.password),
                "VERA_COOKIE_SECURE": "false",
            },
            clear=False,
        )
        self.environment.start()
        initialize_storage()
        app = FastAPI()
        app.include_router(auth_router)
        app.include_router(control_router)
        self.client = TestClient(app)
        login = self.client.post(
            "/api/auth/login", json={"username": "bruce", "password": self.password}
        )
        self.csrf = login.json()["csrf_token"]

    def tearDown(self):
        self.client.close()
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_stop_and_explicit_resume_are_audited(self):
        initial = self.client.get("/api/vera/control").json()["control"]
        stopped = self.client.post(
            "/api/vera/control/emergency-stop",
            headers={"X-CSRF-Token": self.csrf},
            json={"reason": "Router test", "expected_version": initial["version"]},
        )
        self.assertEqual(stopped.status_code, 200)
        stopped_control = stopped.json()["control"]
        self.assertEqual(stopped_control["mode"], "emergency_stop")

        no_csrf = self.client.post("/api/vera/control/resume", json={})
        self.assertEqual(no_csrf.status_code, 403)

        resumed = self.client.post(
            "/api/vera/control/resume",
            headers={"X-CSRF-Token": self.csrf},
            json={
                "reason": "Explicit router test resume",
                "expected_version": stopped_control["version"],
            },
        )
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json()["control"]["mode"], "active")

        events = self.client.get("/api/vera/audit").json()["events"]
        self.assertEqual([event["action"] for event in events[:2]], ["control.active", "control.emergency_stop"])

    def test_stale_version_returns_conflict(self):
        initial = self.client.get("/api/vera/control").json()["control"]
        self.client.post(
            "/api/vera/control/pause",
            headers={"X-CSRF-Token": self.csrf},
            json={"expected_version": initial["version"]},
        )
        stale = self.client.post(
            "/api/vera/control/resume",
            headers={"X-CSRF-Token": self.csrf},
            json={"expected_version": initial["version"]},
        )
        self.assertEqual(stale.status_code, 409)


if __name__ == "__main__":
    unittest.main()
