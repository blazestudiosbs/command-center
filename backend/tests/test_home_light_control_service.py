import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from services import home_assistant_service, policy_service
from storage import connection, initialize_storage


class HomeLightControlServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"VERA_DATABASE_PATH": os.path.join(self.temp_dir.name, "vera.db"), "HOME_ASSISTANT_URL": "http://homeassistant:8123", "HOME_ASSISTANT_TOKEN": "secret"}, clear=False)
        self.environment.start()
        initialize_storage()
        with connection() as conn:
            conn.execute("INSERT INTO users (id,username,password_hash,role,active,created_utc,updated_utc) VALUES ('owner','bruce','test','owner',1,'2026-08-26T00:00:00Z','2026-08-26T00:00:00Z')")

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_only_light_entities_can_receive_permission(self):
        with self.assertRaises(ValueError):
            home_assistant_service.set_light_permission("owner", "lock.front_door", True)
        permission = home_assistant_service.set_light_permission("owner", "light.kitchen", True)
        self.assertTrue(permission["enabled"])

    def test_action_requires_device_permission(self):
        with self.assertRaises(PermissionError):
            home_assistant_service.prepare_light_action("owner", entity_id="light.kitchen", action="turn_off")

    def test_confirm_rechecks_permission_and_calls_only_light_service(self):
        home_assistant_service.set_light_permission("owner", "light.kitchen", True)
        with patch.object(home_assistant_service, "_entity", return_value={"entity_id": "light.kitchen", "name": "Kitchen", "state": "on"}):
            prepared = home_assistant_service.prepare_light_action("owner", entity_id="light.kitchen", action="turn_off")
        response = Mock()
        response.raise_for_status.return_value = None
        with patch.object(home_assistant_service.requests, "post", return_value=response) as post, patch.object(home_assistant_service, "_entity", return_value={"entity_id": "light.kitchen", "name": "Kitchen", "state": "off"}):
            result = home_assistant_service.confirm_light_action("owner", prepared["id"])
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["verified"])
        self.assertEqual(post.call_args.args[0], "http://homeassistant:8123/api/services/light/turn_off")
        self.assertEqual(post.call_args.kwargs["json"], {"entity_id": "light.kitchen"})

    def test_revoked_device_permission_blocks_pending_confirmation(self):
        home_assistant_service.set_light_permission("owner", "light.kitchen", True)
        with patch.object(home_assistant_service, "_entity", return_value={"entity_id": "light.kitchen", "name": "Kitchen", "state": "on"}):
            prepared = home_assistant_service.prepare_light_action("owner", entity_id="light.kitchen", action="turn_off")
        home_assistant_service.set_light_permission("owner", "light.kitchen", False)
        with self.assertRaises(PermissionError):
            home_assistant_service.confirm_light_action("owner", prepared["id"])

    def test_unavailable_light_cannot_be_prepared(self):
        home_assistant_service.set_light_permission("owner", "light.kitchen", True)
        with patch.object(home_assistant_service, "_entity", return_value={"entity_id": "light.kitchen", "name": "Kitchen", "state": "unavailable"}):
            with self.assertRaises(RuntimeError):
                home_assistant_service.prepare_light_action("owner", entity_id="light.kitchen", action="turn_off")

    def test_emergency_stop_blocks_confirmation_before_service_call(self):
        home_assistant_service.set_light_permission("owner", "light.kitchen", True)
        with patch.object(home_assistant_service, "_entity", return_value={"entity_id": "light.kitchen", "name": "Kitchen", "state": "on"}):
            prepared = home_assistant_service.prepare_light_action("owner", entity_id="light.kitchen", action="turn_off")
        policy_service.set_control_mode(mode="emergency_stop", actor_user_id="owner", reason="test")
        with patch.object(home_assistant_service.requests, "post") as post, self.assertRaises(policy_service.PolicyDeniedError):
            home_assistant_service.confirm_light_action("owner", prepared["id"])
        post.assert_not_called()

    def test_mismatched_observed_state_is_not_completed(self):
        home_assistant_service.set_light_permission("owner", "light.kitchen", True)
        with patch.object(home_assistant_service, "_entity", return_value={"entity_id": "light.kitchen", "name": "Kitchen", "state": "on"}):
            prepared = home_assistant_service.prepare_light_action("owner", entity_id="light.kitchen", action="turn_off")
        response = Mock()
        response.raise_for_status.return_value = None
        with patch.object(home_assistant_service.requests, "post", return_value=response), patch.object(home_assistant_service, "_entity", return_value={"entity_id": "light.kitchen", "name": "Kitchen", "state": "on"}), self.assertRaises(RuntimeError):
            home_assistant_service.confirm_light_action("owner", prepared["id"])
        with connection() as conn:
            status = conn.execute("SELECT status FROM home_light_action_requests WHERE id=?", (prepared["id"],)).fetchone()["status"]
        self.assertEqual(status, "failed")

    def test_direct_control_supports_brightness_color_and_effect(self):
        home_assistant_service.set_light_permission("owner", "light.kitchen", True)
        before = {"entity_id": "light.kitchen", "name": "Kitchen", "state": "off", "brightness": None, "color_temp_kelvin": None, "rgb_color": None, "effect": None, "supported_color_modes": ["color_temp", "rgb"], "effect_list": ["rainbow"], "min_color_temp_kelvin": 2200, "max_color_temp_kelvin": 6500}
        after = {**before, "state": "on", "brightness": 200, "rgb_color": [255, 0, 0], "effect": "rainbow"}
        response = Mock(); response.raise_for_status.return_value = None
        with patch.object(home_assistant_service, "_entity", side_effect=[before, after]), patch.object(home_assistant_service.requests, "post", return_value=response) as post:
            result = home_assistant_service.execute_light_action("owner", entity_id="light.kitchen", action="turn_on", brightness=200, rgb_color=(255, 0, 0), effect="rainbow")
        self.assertTrue(result["verified"])
        self.assertEqual(post.call_args.kwargs["json"], {"entity_id": "light.kitchen", "brightness": 200, "rgb_color": [255, 0, 0], "effect": "rainbow"})

    def test_emergency_stop_blocks_direct_control(self):
        home_assistant_service.set_light_permission("owner", "light.kitchen", True)
        entity = {"entity_id": "light.kitchen", "name": "Kitchen", "state": "off", "brightness": None, "color_temp_kelvin": None, "rgb_color": None, "effect": None, "supported_color_modes": ["rgb"], "effect_list": [], "min_color_temp_kelvin": 2200, "max_color_temp_kelvin": 6500}
        policy_service.set_control_mode(mode="emergency_stop", actor_user_id="owner", reason="test")
        with patch.object(home_assistant_service, "_entity", return_value=entity), patch.object(home_assistant_service.requests, "post") as post, self.assertRaises(policy_service.PolicyDeniedError):
            home_assistant_service.execute_light_action("owner", entity_id="light.kitchen", action="turn_on")
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
