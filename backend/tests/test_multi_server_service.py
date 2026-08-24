import os
import tempfile
import unittest
from unittest.mock import patch

from services import multi_server_service
from storage import connection, initialize_storage


class MultiServerServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"VERA_DATABASE_PATH": os.path.join(self.temp_dir.name, "vera.db")}, clear=False)
        self.environment.start()
        initialize_storage()
        with connection() as conn:
            conn.execute("INSERT INTO users (id,username,password_hash,role,active,created_utc,updated_utc) VALUES ('owner','bruce','test','owner',1,'2026-08-24T00:00:00Z','2026-08-24T00:00:00Z')")

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_registration_returns_token_once_and_stores_only_hash(self):
        registered = multi_server_service.register("owner", name="Media Server", hostname="media.tailnet")
        self.assertTrue(registered["enrollment_token"])
        listed = multi_server_service.list_servers("owner")[0]
        self.assertNotIn("enrollment_token", listed)
        self.assertNotIn("token_hash", listed)
        self.assertEqual(listed["connection_status"], "awaiting_first_report")
        with connection() as conn:
            stored = conn.execute("SELECT token_hash FROM managed_servers").fetchone()[0]
        self.assertNotEqual(stored, registered["enrollment_token"])

    def test_valid_heartbeat_updates_read_only_status(self):
        registered = multi_server_service.register("owner", name="Media Server", hostname="media")
        status = {"uptime_seconds": 100, "load_1m": 0.2, "memory_used_percent": 31.5, "disk_used_percent": 42.0, "services_running": 4, "services_total": 5}
        server = multi_server_service.record_heartbeat(registered["enrollment_token"], agent_version="1.0", status=status)
        self.assertEqual(server["connection_status"], "online")
        self.assertEqual(server["status"], status)

    def test_disable_rejects_heartbeats_and_rotation_invalidates_old_token(self):
        registered = multi_server_service.register("owner", name="Media Server", hostname="media")
        server_id, old_token = registered["id"], registered["enrollment_token"]
        rotated = multi_server_service.rotate_token("owner", server_id)
        with self.assertRaises(PermissionError):
            multi_server_service.record_heartbeat(old_token, agent_version="1.0", status={})
        multi_server_service.set_enabled("owner", server_id, False)
        with self.assertRaises(PermissionError):
            multi_server_service.record_heartbeat(rotated["enrollment_token"], agent_version="1.0", status={})


if __name__ == "__main__":
    unittest.main()
