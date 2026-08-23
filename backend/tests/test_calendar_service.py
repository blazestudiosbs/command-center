import unittest
from datetime import datetime
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from services import calendar_service, gmail_service


class CalendarServiceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
