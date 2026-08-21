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
                "VERA_LOCAL_MODEL": "test-model",
                "VERA_OLLAMA_URL": "http://ollama.test",
            },
            clear=False,
        )
        self.environment.start()
        initialize_storage()
        auth_service.sync_owner()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    @patch("services.vera_conversation_service.requests.post")
    def test_response_persists_user_and_assistant_and_is_idempotent(self, post):
        post.return_value.json.return_value = {
            "message": {"content": "private reasoning\n<vera_final>Hello Bruce</vera_final>"}
        }
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
        self.assertEqual(post.call_count, 1)
        sent_messages = post.call_args.kwargs["json"]["messages"]
        self.assertTrue(sent_messages[-1]["content"].endswith("/no_think"))
        self.assertEqual(post.call_args.kwargs["json"]["options"]["num_predict"], 512)

    def test_local_output_limit_is_bounded(self):
        with patch.dict(os.environ, {"VERA_LOCAL_MAX_OUTPUT_TOKENS": "900"}):
            self.assertEqual(vera_conversation_service._local_max_output_tokens(), 900)
        with patch.dict(os.environ, {"VERA_LOCAL_MAX_OUTPUT_TOKENS": "999999"}):
            self.assertEqual(vera_conversation_service._local_max_output_tokens(), 512)
        with patch.dict(os.environ, {"VERA_LOCAL_MAX_OUTPUT_TOKENS": "invalid"}):
            self.assertEqual(vera_conversation_service._local_max_output_tokens(), 512)

    def test_rejects_unclosed_or_untagged_reasoning(self):
        self.assertEqual(vera_conversation_service._clean_model_text("<think>still reasoning"), "")
        self.assertEqual(
            vera_conversation_service._clean_model_text("Okay, let's tackle this. The answer should be short."),
            "",
        )
        self.assertEqual(
            vera_conversation_service._clean_model_text(
                "We are in a Discord conversation. The user (Bruce) is asking...",
                require_final_envelope=True,
            ),
            "",
        )
        self.assertEqual(
            vera_conversation_service._clean_model_text(
                "analysis outside<vera_final>Safe answer</vera_final>",
                require_final_envelope=True,
            ),
            "Safe answer",
        )

    @patch("services.vera_conversation_service.openai_service.get_model", return_value="gpt-4.1-mini")
    @patch("services.vera_conversation_service.cloud_response_service.run_guarded")
    @patch("services.vera_conversation_service.router_service.cloud_routing_enabled", return_value=True)
    @patch("services.vera_conversation_service.requests.post", side_effect=RuntimeError("local unavailable"))
    def test_local_failure_uses_guarded_cloud_only_when_enabled(
        self, _post, _enabled, run_guarded, _model
    ):
        run_guarded.return_value = (
            SimpleNamespace(output_text="<vera_final>Cloud fallback response</vera_final>"),
            {"actual_cost_usd": 0.001},
        )
        conversation = conversation_service.create_conversation("owner", "Discord")
        result = vera_conversation_service.respond(
            owner_user_id="owner",
            conversation_id=conversation["id"],
            content="Hello Vera",
            client_message_id="discord:cloud-1",
            source="discord",
        )
        assistant = result["assistant_message"]
        self.assertEqual(assistant["content"], "Cloud fallback response")
        self.assertEqual(assistant["model"], "gpt-4.1-mini")
        self.assertEqual(assistant["metadata"]["provider"], "openai")
        self.assertEqual(run_guarded.call_args.kwargs["domain"], "conversation")

    @patch("services.vera_conversation_service.cloud_response_service.run_guarded")
    @patch("services.vera_conversation_service.router_service.cloud_routing_enabled", return_value=False)
    @patch("services.vera_conversation_service.requests.post", side_effect=RuntimeError("local unavailable"))
    def test_local_failure_does_not_use_cloud_when_disabled(self, _post, _enabled, run_guarded):
        conversation = conversation_service.create_conversation("owner", "Discord")
        with self.assertRaisesRegex(RuntimeError, "local unavailable"):
            vera_conversation_service.respond(
                owner_user_id="owner",
                conversation_id=conversation["id"],
                content="Hello Vera",
                client_message_id="discord:local-only-1",
                source="discord",
            )
        run_guarded.assert_not_called()


if __name__ == "__main__":
    unittest.main()
