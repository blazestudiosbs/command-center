import os
import tempfile
import unittest
from unittest.mock import patch

from services import audit_service, budget_service, decision_journal_service
from storage import initialize_storage


class DecisionJournalServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {"VERA_DATABASE_PATH": os.path.join(self.temp_dir.name, "vera.db")},
            clear=False,
        )
        self.environment.start()
        initialize_storage()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_journal_combines_route_and_cost_metadata_without_prompts(self):
        audit_service.append_event(
            action="conversation.route",
            resource_type="conversation",
            outcome="succeeded",
            details={"route": "openai", "model": "gpt-4.1-mini", "local_error_type": "ConnectionError"},
        )
        budget_service.simulate(prompt="private prompt", max_output_tokens=50)

        entries = decision_journal_service.list_entries()

        self.assertEqual({entry["kind"] for entry in entries}, {"route", "simulation"})
        self.assertNotIn("private prompt", str(entries))
        route = next(entry for entry in entries if entry["kind"] == "route")
        self.assertEqual(route["provider"], "openai")
        self.assertIn("ConnectionError", route["reason"])


if __name__ == "__main__":
    unittest.main()
