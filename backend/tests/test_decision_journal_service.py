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

    def test_journal_groups_response_and_paginates_complete_relevant_history(self):
        for index in range(110):
            audit_service.append_event(
                action="unrelated.read",
                resource_type="status",
                outcome="succeeded",
                request_id=f"unrelated:{index}",
            )
        audit_service.append_event(
            action="conversation.route",
            resource_type="conversation",
            outcome="succeeded",
            request_id="discord:grouped",
            details={"route": "local", "model": "qwen3:4b-instruct"},
        )
        audit_service.append_event(
            action="conversation.response",
            resource_type="conversation",
            outcome="succeeded",
            request_id="discord:grouped",
            details={"provider": "local", "model": "qwen3:4b-instruct"},
        )
        audit_service.append_event(
            action="cloud_routing.disabled",
            resource_type="cloud_routing_state",
            outcome="succeeded",
            details={"reason": "Test complete"},
        )

        first = decision_journal_service.get_page(limit=1)
        second = decision_journal_service.get_page(limit=1, offset=1)

        self.assertEqual(first["summary"]["total_entries"], 2)
        self.assertEqual(first["summary"]["local_routes"], 1)
        self.assertEqual(len(first["entries"]), 1)
        self.assertTrue(first["has_more"])
        self.assertEqual(len(second["entries"]), 1)
        self.assertFalse(second["has_more"])


if __name__ == "__main__":
    unittest.main()
