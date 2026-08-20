import os
import unittest
from enum import Enum
from types import SimpleNamespace
from unittest.mock import patch

from services import openai_service


class OpenAIServiceTests(unittest.TestCase):
    def tearDown(self):
        openai_service.get_client.cache_clear()

    def test_missing_key_disables_cloud_client(self):
        with patch.dict(os.environ, {}, clear=True):
            openai_service.get_client.cache_clear()
            self.assertIsNone(openai_service.get_client())
            self.assertEqual(
                openai_service.get_status(),
                {
                    "provider": "openai",
                    "configured": False,
                    "status": "not_configured",
                    "connection_status": "disabled",
                    "model": "gpt-4.1-mini",
                    "detail": "OPENAI_API_KEY is not configured; cloud requests are disabled.",
                },
            )

    def test_blank_key_is_treated_as_missing(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "   "}, clear=True):
            openai_service.get_client.cache_clear()
            self.assertFalse(openai_service.is_configured())
            self.assertIsNone(openai_service.get_client())

    def test_status_never_includes_the_key(self):
        secret = "sk-example-do-not-use"
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": secret, "OPENAI_MODEL": "test-model"},
            clear=True,
        ):
            status = openai_service.get_status()
            self.assertTrue(status["configured"])
            self.assertEqual(status["status"], "configured")
            self.assertEqual(status["model"], "test-model")
            self.assertNotIn(secret, str(status))

    def test_response_status_includes_incomplete_reason(self):
        class Reason(Enum):
            MAX_OUTPUT_TOKENS = "max_output_tokens"

        response = SimpleNamespace(
            status="incomplete",
            incomplete_details=SimpleNamespace(reason=Reason.MAX_OUTPUT_TOKENS),
        )
        self.assertEqual(
            openai_service.get_response_status(response),
            ("incomplete", "max_output_tokens"),
        )


if __name__ == "__main__":
    unittest.main()
