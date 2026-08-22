import os
import unittest
from unittest.mock import Mock, patch

from services import home_assistant_service


class HomeAssistantServiceTests(unittest.TestCase):
    def test_missing_configuration_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            result = home_assistant_service.get_overview()
        self.assertFalse(result["status"]["configured"])
        self.assertEqual(result["entities"], [])

    @patch("services.home_assistant_service.requests.get")
    def test_overview_returns_only_safe_read_only_entity_fields(self, get):
        root = Mock()
        states = Mock()
        states.json.return_value = [{
            "entity_id": "light.kitchen",
            "state": "on",
            "last_changed": "2026-08-21T12:00:00Z",
            "attributes": {"friendly_name": "Kitchen", "secret": "hidden"},
        }]
        get.side_effect = [root, states]
        with patch.dict(os.environ, {
            "HOME_ASSISTANT_URL": "http://homeassistant.local:8123",
            "HOME_ASSISTANT_TOKEN": "secret-token",
        }, clear=True):
            result = home_assistant_service.get_overview()
        self.assertEqual(result["entities"][0]["name"], "Kitchen")
        self.assertNotIn("secret", str(result))
        self.assertNotIn("secret-token", str(result))
        self.assertEqual(get.call_args_list[1].args[0], "http://homeassistant.local:8123/api/states")


if __name__ == "__main__":
    unittest.main()
