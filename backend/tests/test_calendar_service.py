import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from services import calendar_service, gmail_service
from storage import connection, initialize_storage


class CalendarServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"VERA_DATABASE_PATH": os.path.join(self.temp_dir.name, "vera.db")}, clear=False)
        self.environment.start()
        initialize_storage()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    @patch("services.calendar_service.gmail_service.get_status")
    def test_status_requires_calendar_scope(self, gmail_status):
        gmail_status.return_value = {"configured": True, "connected": True, "email_address": "bruce@example.com", "scopes": [gmail_service.GMAIL_MODIFY_SCOPE]}
        self.assertFalse(calendar_service.get_status("owner")["connected"])
        gmail_status.return_value["scopes"].append(gmail_service.CALENDAR_READONLY_SCOPE)
        self.assertTrue(calendar_service.get_status("owner")["connected"])

    @patch("services.calendar_service.requests.get")
    @patch("services.calendar_service.gmail_service._access_token", return_value="token")
    @patch("services.calendar_service.get_status", return_value={"connected": True})
    def test_event_list_is_read_only_and_excludes_bodies(self, _status, _token, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"items": [{
            "id": "e1", "summary": "Dentist", "description": "private notes",
            "start": {"dateTime": "2026-08-24T10:00:00-04:00"},
            "end": {"dateTime": "2026-08-24T11:00:00-04:00"},
            "location": "Office", "status": "confirmed", "htmlLink": "https://calendar.google.com/event",
        }]}
        get.return_value = response
        zone = ZoneInfo("America/Detroit")
        events = calendar_service.list_events("owner", start=datetime(2026, 8, 24, tzinfo=zone), end=datetime(2026, 8, 25, tzinfo=zone))
        self.assertEqual(events[0]["title"], "Dentist")
        self.assertNotIn("description", events[0])
        self.assertNotIn("attendees", events[0])
        self.assertEqual(get.call_args.kwargs["params"]["singleEvents"], "true")

    @patch("services.calendar_service.requests.get")
    @patch("services.calendar_service.get_status", return_value={"write_authorized": True})
    def test_edit_is_pending_and_records_current_event(self, _status, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"id": "event-1", "etag": "v1", "summary": "Old title", "start": {"dateTime": "2026-08-24T10:00:00-04:00"}, "end": {"dateTime": "2026-08-24T11:00:00-04:00"}, "status": "confirmed"}
        get.return_value = response
        with patch("services.calendar_service.gmail_service._access_token", return_value="token"):
            change = calendar_service.prepare_change("owner", action="edit", event_id="event-1", title="New title", start="2026-08-24T12:00", end="2026-08-24T13:00", location="Home", all_day=False)
        self.assertEqual(change["status"], "pending")
        self.assertEqual(change["before"]["title"], "Old title")
        self.assertEqual(change["after"]["title"], "New title")
        with connection() as conn:
            row = conn.execute("SELECT status, event_etag FROM calendar_change_requests WHERE id = ?", (change["id"],)).fetchone()
        self.assertEqual((row["status"], row["event_etag"]), ("pending", "v1"))

    @patch("services.calendar_service.requests.patch")
    @patch("services.calendar_service.requests.get")
    @patch("services.calendar_service.get_status", return_value={"write_authorized": True})
    def test_confirmed_edit_uses_etag_and_cannot_repeat(self, _status, get, patch_request):
        current = Mock(); current.raise_for_status.return_value = None
        current.json.return_value = {"id": "event-1", "etag": "v1", "summary": "Old", "start": {"dateTime": "2026-08-24T10:00:00-04:00"}, "end": {"dateTime": "2026-08-24T11:00:00-04:00"}, "status": "confirmed"}
        get.return_value = current
        updated = Mock(); updated.raise_for_status.return_value = None
        updated.json.return_value = {"id": "event-1", "summary": "New", "start": {"dateTime": "2026-08-24T12:00:00-04:00"}, "end": {"dateTime": "2026-08-24T13:00:00-04:00"}, "status": "confirmed"}
        patch_request.return_value = updated
        with patch("services.calendar_service.gmail_service._access_token", return_value="token"):
            change = calendar_service.prepare_change("owner", action="edit", event_id="event-1", title="New", start="2026-08-24T12:00", end="2026-08-24T13:00", all_day=False)
            result = calendar_service.confirm_change("owner", change["id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(patch_request.call_args.kwargs["headers"]["If-Match"], "v1")
        with self.assertRaises(ValueError):
            calendar_service.confirm_change("owner", change["id"])


if __name__ == "__main__":
    unittest.main()
