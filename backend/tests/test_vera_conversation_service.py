import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services import auth_service, conversation_service, vera_conversation_service
from storage import initialize_storage


class VeraConversationServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {
                "VERA_DATABASE_PATH": os.path.join(self.temp_dir.name, "vera.db"),
                "VERA_ADMIN_PASSWORD_HASH": auth_service.hash_password("correct horse battery staple"),
                "OPENAI_API_KEY": "test-key",
                "OPENAI_MODEL": "test-model",
            },
            clear=False,
        )
        self.environment.start()
        initialize_storage()
        auth_service.sync_owner()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    @patch("services.vera_conversation_service.OpenAI")
    def test_response_persists_user_and_assistant_and_is_idempotent(self, openai):
        openai.return_value.responses.create.return_value = SimpleNamespace(output_text="Hello Bruce")
        conversation = conversation_service.create_conversation("owner", "Discord")
        result = vera_conversation_service.respond(
            owner_user_id="owner",
            conversation_id=conversation["id"],
            content="Hello Vera",
            client_message_id="discord:1",
            source="discord",
        )
        duplicate = vera_conversation_service.respond(
            owner_user_id="owner",
            conversation_id=conversation["id"],
            content="Hello Vera",
            client_message_id="discord:1",
            source="discord",
        )
        messages = conversation_service.list_messages(conversation["id"], "owner")
        self.assertEqual([message["content"] for message in messages], ["Hello Vera", "Hello Bruce"])
        self.assertFalse(result["duplicate"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(openai.return_value.responses.create.call_count, 1)


if __name__ == "__main__":
    unittest.main()
