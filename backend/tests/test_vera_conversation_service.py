import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services import auth_service, conversation_service, service_monitoring_service, vera_conversation_service
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

    @patch("services.vera_conversation_service.requests.post")
    @patch("services.vera_conversation_service.cloud_response_service.run_guarded")
    def test_service_status_question_uses_deterministic_local_answer(self, run_guarded, post):
        snapshot = {
            name: {"status": "running", "detail": "Docker status: running."}
            for name in service_monitoring_service.configured_containers()
        }
        snapshot["plex"] = {"status": "stopped", "detail": "Docker status: exited."}
        service_monitoring_service.record_snapshot(snapshot, now="2026-08-21T12:00:00Z")
        conversation = conversation_service.create_conversation("owner", "Discord")

        result = vera_conversation_service.respond(
            owner_user_id="owner",
            conversation_id=conversation["id"],
            content="Vera, are my services running?",
            client_message_id="discord:monitoring-1",
            source="discord",
        )

        answer = result["assistant_message"]
        self.assertIn("Unavailable: Plex (stopped)", answer["content"])
        self.assertEqual(answer["model"], "vera-monitoring")
        self.assertEqual(answer["metadata"]["provider"], "local")
        post.assert_not_called()
        run_guarded.assert_not_called()

    @patch("services.vera_conversation_service.requests.post")
    def test_specific_service_question_uses_stored_status(self, post):
        snapshot = {
            name: {"status": "running", "detail": "Docker status: running."}
            for name in service_monitoring_service.configured_containers()
        }
        service_monitoring_service.record_snapshot(snapshot, now="2026-08-21T12:00:00Z")
        conversation = conversation_service.create_conversation("owner", "Discord")

        result = vera_conversation_service.respond(
            owner_user_id="owner",
            conversation_id=conversation["id"],
            content="Is Minecraft up?",
            client_message_id="discord:monitoring-2",
            source="discord",
        )

        self.assertIn("Minecraft is running", result["assistant_message"]["content"])
        post.assert_not_called()

    @patch("services.vera_conversation_service.requests.post")
    @patch("services.vera_conversation_service.cloud_response_service.run_guarded")
    def test_recent_incident_question_uses_local_audit_history(self, run_guarded, post):
        running = {
            name: {"status": "running", "detail": "running"}
            for name in service_monitoring_service.configured_containers()
        }
        stopped = dict(running)
        stopped["plex"] = {"status": "stopped", "detail": "exited"}
        with patch("services.service_monitoring_service.discord_alert_service.send", return_value={"sent": False}):
            service_monitoring_service.record_snapshot(running, now="2026-08-21T12:00:00Z")
            service_monitoring_service.record_snapshot(stopped, now="2026-08-21T12:01:00Z")
            service_monitoring_service.record_snapshot(running, now="2026-08-21T12:02:00Z")
        conversation = conversation_service.create_conversation("owner", "Discord")

        result = vera_conversation_service.respond(
            owner_user_id="owner",
            conversation_id=conversation["id"],
            content="When did Plex recover?",
            client_message_id="discord:monitoring-history-1",
            source="discord",
        )

        answer = result["assistant_message"]["content"]
        self.assertIn("Plex: recovery at 2026-08-21T12:02:00Z", answer)
        self.assertEqual(result["assistant_message"]["model"], "vera-monitoring")
        post.assert_not_called()
        run_guarded.assert_not_called()

    @patch("services.vera_conversation_service.requests.post")
    def test_empty_incident_history_has_clear_local_answer(self, post):
        conversation = conversation_service.create_conversation("owner", "Discord")
        result = vera_conversation_service.respond(
            owner_user_id="owner",
            conversation_id=conversation["id"],
            content="Were there any recent outages?",
            client_message_id="discord:monitoring-history-2",
            source="discord",
        )

        self.assertIn("no matching recent incidents", result["assistant_message"]["content"])
        post.assert_not_called()

    @patch("services.vera_conversation_service.requests.post")
    @patch("services.vera_conversation_service.gmail_service.search_metadata")
    @patch("services.vera_conversation_service.gmail_service.get_status", return_value={"connected": True})
    def test_recent_email_question_uses_local_gmail_metadata(self, _status, search, post):
        from services import agent_permission_service
        agent_permission_service.set_permission(
            user_id="owner", agent_id="gmail", capability="read_inbox", enabled=True
        )
        search.return_value = [
            {"message_id": "m1", "subject": "Your order shipped", "sender": "Store <store@example.com>"}
        ]
        conversation = conversation_service.create_conversation("owner", "Discord")
        result = vera_conversation_service.respond(
            owner_user_id="owner", conversation_id=conversation["id"],
            content="Do I have any new emails?", client_message_id="discord:gmail-1", source="discord",
        )
        self.assertIn("Your order shipped", result["assistant_message"]["content"])
        self.assertEqual(search.call_args.args[1], "is:unread newer_than:7d")
        post.assert_not_called()

    @patch("services.vera_conversation_service.requests.post")
    def test_disabled_gmail_permission_returns_local_guidance(self, post):
        conversation = conversation_service.create_conversation("owner", "Discord")
        result = vera_conversation_service.respond(
            owner_user_id="owner", conversation_id=conversation["id"],
            content="Do I have unread email?", client_message_id="discord:gmail-2", source="discord",
        )
        self.assertIn("permission is off", result["assistant_message"]["content"])
        post.assert_not_called()

    @patch("services.vera_conversation_service.requests.post")
    @patch("services.vera_conversation_service.gmail_rule_service.propose")
    def test_permanent_delete_request_creates_pending_rule_locally(self, propose, post):
        propose.return_value = {
            "sender": "store-news@amazon.com", "validation_match_count": 7, "status": "pending"
        }
        conversation = conversation_service.create_conversation("owner", "Discord")
        result = vera_conversation_service.respond(
            owner_user_id="owner", conversation_id=conversation["id"],
            content="Anything new or old from store-news@amazon.com can be permanently deleted.",
            client_message_id="discord:gmail-rule-1", source="discord",
        )
        self.assertIn("pending—not active", result["assistant_message"]["content"])
        self.assertIn("7 existing matching messages", result["assistant_message"]["content"])
        propose.assert_called_once_with("owner", "store-news@amazon.com", source="discord")
        post.assert_not_called()

    @patch("services.vera_conversation_service.requests.post")
    @patch("services.vera_conversation_service.gmail_rule_service.propose")
    def test_follow_up_can_create_rule_from_prior_discord_request(self, propose, post):
        propose.return_value = {
            "sender": "store-news@amazon.com", "validation_match_count": 3, "status": "pending"
        }
        conversation = conversation_service.create_conversation("owner", "Discord")
        conversation_service.add_message(
            conversation_id=conversation["id"], owner_user_id="owner", role="user",
            content="Permanently delete mail from store-news@amazon.com.",
        )
        conversation_service.add_message(
            conversation_id=conversation["id"], owner_user_id="owner", role="assistant",
            content="Would you like a Gmail rule?",
        )
        result = vera_conversation_service.respond(
            owner_user_id="owner", conversation_id=conversation["id"],
            content="Yes, make that rule", client_message_id="discord:gmail-rule-follow-up", source="discord",
        )
        self.assertIn("pending—not active", result["assistant_message"]["content"])
        propose.assert_called_once_with("owner", "store-news@amazon.com", source="discord")
        post.assert_not_called()

    @patch("services.vera_conversation_service.requests.post")
    @patch("services.vera_conversation_service.calendar_service.list_events")
    @patch("services.vera_conversation_service.calendar_service.get_status", return_value={"connected": True})
    def test_calendar_question_uses_local_read_only_agent(self, _status, events, post):
        from services import agent_permission_service
        agent_permission_service.set_permission(user_id="owner", agent_id="calendar", capability="read_events", enabled=True)
        events.return_value = [{"id": "e1", "title": "Dentist", "start": "2026-08-24T10:00:00-04:00", "end": "2026-08-24T11:00:00-04:00", "all_day": False, "location": "Office"}]
        conversation = conversation_service.create_conversation("owner", "Discord")
        result = vera_conversation_service.respond(owner_user_id="owner", conversation_id=conversation["id"], content="What is on my calendar tomorrow?", client_message_id="discord:calendar-1", source="discord")
        self.assertIn("Dentist", result["assistant_message"]["content"])
        self.assertIn("Office", result["assistant_message"]["content"])
        post.assert_not_called()

    @patch("services.vera_conversation_service.requests.post")
    @patch("services.vera_conversation_service.calendar_service.prepare_change")
    @patch("services.vera_conversation_service.calendar_service.get_status", return_value={"write_authorized": True})
    def test_calendar_create_request_prepares_confirmation_instead_of_listing_events(self, _status, prepare, post):
        from services import agent_permission_service
        agent_permission_service.set_permission(user_id="owner", agent_id="calendar", capability="create", enabled=True)
        prepare.return_value = {"id": "change-1", "status": "pending"}
        conversation = conversation_service.create_conversation("owner", "Discord")
        result = vera_conversation_service.respond(owner_user_id="owner", conversation_id=conversation["id"], content="Can you create a calander event to have lunch with Sara tomorrow at 1230pm please?", client_message_id="discord:calendar-create-1", source="discord")
        self.assertIn("Lunch with Sara", result["assistant_message"]["content"])
        self.assertIn("pending—not active", result["assistant_message"]["content"])
        kwargs = prepare.call_args.kwargs
        self.assertEqual(kwargs["action"], "create")
        self.assertEqual(kwargs["title"], "Lunch with Sara")
        self.assertIn("T12:30:00", kwargs["start"])
        post.assert_not_called()

    @patch("services.vera_conversation_service.requests.post")
    @patch("services.vera_conversation_service.calendar_service.prepare_change")
    @patch("services.vera_conversation_service.calendar_service.list_events")
    @patch("services.vera_conversation_service.calendar_service.get_status", return_value={"write_authorized": True})
    def test_calendar_edit_request_matches_event_and_preserves_duration(self, _status, events, prepare, post):
        from services import agent_permission_service
        agent_permission_service.set_permission(user_id="owner", agent_id="calendar", capability="edit", enabled=True)
        events.return_value = [{"id": "event-1", "title": "Work Day", "start": "2026-08-24T19:00:00-04:00", "end": "2026-08-24T20:30:00-04:00", "all_day": False, "location": "Office"}]
        conversation = conversation_service.create_conversation("owner", "Discord")
        result = vera_conversation_service.respond(owner_user_id="owner", conversation_id=conversation["id"], content="Move Work Day tomorrow to 8pm", client_message_id="discord:calendar-edit-1", source="discord")
        self.assertIn("pending—not active", result["assistant_message"]["content"])
        kwargs = prepare.call_args.kwargs
        self.assertEqual(kwargs["action"], "edit")
        self.assertEqual(kwargs["event_id"], "event-1")
        self.assertIn("T20:00:00", kwargs["start"])
        self.assertIn("T21:30:00", kwargs["end"])
        post.assert_not_called()

    @patch("services.vera_conversation_service.calendar_service.list_events", return_value=[])
    @patch("services.vera_conversation_service.calendar_service.get_status", return_value={"write_authorized": True})
    def test_calendar_edit_request_fails_closed_when_no_event_matches(self, _status, _events):
        from services import agent_permission_service
        agent_permission_service.set_permission(user_id="owner", agent_id="calendar", capability="edit", enabled=True)
        conversation = conversation_service.create_conversation("owner", "Discord")
        result = vera_conversation_service.respond(owner_user_id="owner", conversation_id=conversation["id"], content="Move Dentist tomorrow to 8pm", client_message_id="discord:calendar-edit-missing", source="discord")
        self.assertIn("No change was prepared", result["assistant_message"]["content"])

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
        self.assertEqual(
            vera_conversation_service._clean_model_text(
                "We are in a Discord conversation. The user (Bruce) is asking..."
            ),
            "",
        )

    @patch("services.vera_conversation_service.openai_service.get_model", return_value="gpt-4.1-mini")
    @patch("services.vera_conversation_service.cloud_response_service.run_guarded")
    @patch("services.vera_conversation_service.router_service.cloud_routing_enabled", return_value=True)
    @patch("services.vera_conversation_service.requests.post", side_effect=RuntimeError("local unavailable"))
    def test_local_failure_uses_guarded_cloud_only_when_enabled(
        self, _post, _enabled, run_guarded, _model
    ):
        run_guarded.return_value = (
            SimpleNamespace(output_text="Cloud fallback response"),
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
