import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import alexa_voice_service, auth_service, conversation_service, household_service
from storage import initialize_storage


class AlexaVoiceServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.secret_path = Path(self.temp_dir.name) / "alexa-secret"
        self.secret = b"a" * 32
        self.secret_path.write_bytes(self.secret)
        self.environment = patch.dict(os.environ, {
            "VERA_DATABASE_PATH": str(Path(self.temp_dir.name) / "vera.db"),
            "VERA_ADMIN_PASSWORD_HASH": auth_service.hash_password("correct horse battery staple"),
            "VERA_ALEXA_RELAY_SECRET_FILE": str(self.secret_path),
        }, clear=False)
        self.environment.start()
        initialize_storage()
        auth_service.sync_owner()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_authentication_accepts_current_signature_and_rejects_replay(self):
        body = json.dumps({"text": "hello"}).encode()
        timestamp = "1000"
        signature = alexa_voice_service.sign(timestamp, body, self.secret)
        alexa_voice_service.authenticate(timestamp=timestamp, signature=signature, body=body, now=1000)
        with self.assertRaises(alexa_voice_service.AlexaRelayAuthenticationError):
            alexa_voice_service.authenticate(timestamp=timestamp, signature=signature, body=body, now=1100)

    def test_signature_covers_body(self):
        timestamp = "1000"
        signature = alexa_voice_service.sign(timestamp, b"original", self.secret)
        with self.assertRaises(alexa_voice_service.AlexaRelayAuthenticationError):
            alexa_voice_service.authenticate(timestamp=timestamp, signature=signature, body=b"changed", now=1000)

    @patch("services.alexa_voice_service.vera_conversation_service.respond")
    def test_session_reuses_persistent_conversation(self, respond):
        respond.side_effect = lambda **kwargs: {
            "duplicate": False,
            "assistant_message": {"content": "Hello from Vera"},
        }
        household_service.link_voice_identity(member_id="owner", provider="amazon_alexa", subject_id="amazon-user-1")
        first = alexa_voice_service.respond(provider="amazon_alexa", subject_id="amazon-user-1", session_id="session-1", request_id="request-1", text="Hello")
        second = alexa_voice_service.respond(provider="amazon_alexa", subject_id="amazon-user-1", session_id="session-1", request_id="request-2", text="Again")
        self.assertEqual(first["conversation_id"], second["conversation_id"])
        self.assertEqual(first["text"], "Hello from Vera")
        self.assertEqual(len(conversation_service.list_conversations("owner")), 1)
        self.assertEqual(respond.call_args.kwargs["source"], "alexa")

    def test_unknown_voice_identity_fails_closed(self):
        with self.assertRaises(household_service.UnlinkedVoiceIdentityError):
            alexa_voice_service.respond(provider="amazon_alexa", subject_id="unknown", session_id="session-2", request_id="request-3", text="Hello")

    def test_spoken_response_is_bounded(self):
        spoken = alexa_voice_service._spoken("word " * 1000)
        self.assertLessEqual(len(spoken), alexa_voice_service.MAX_SPOKEN_CHARS)
        self.assertTrue(spoken.endswith("…"))


if __name__ == "__main__":
    unittest.main()
