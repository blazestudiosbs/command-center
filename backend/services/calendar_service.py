from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

from services import gmail_service
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
LOCAL_TIMEZONE = ZoneInfo("America/Detroit")


def get_status(user_id):
    gmail = gmail_service.get_status(user_id)
    authorized = gmail_service.CALENDAR_READONLY_SCOPE in (gmail.get("scopes") or [])
    return {
        "provider": "google_calendar", "configured": gmail["configured"],
        "connected": gmail["connected"] and authorized, "authorized": authorized,
        "account": gmail.get("email_address"), "access": "read_only",
        "can_create": False, "can_edit": False, "can_delete": False,
        "detail": "Google Calendar is connected with read-only access." if authorized else "Authorize read-only Calendar access with Google.",
    }


def authorization_url(user_id):
    return gmail_service.authorization_url(user_id, calendar_read=True)


def _event(item):
    start = item.get("start") or {}
    end = item.get("end") or {}
    return {
        "id": item.get("id"), "title": item.get("summary") or "Busy",
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "all_day": "date" in start, "location": item.get("location"),
        "status": item.get("status"), "html_url": item.get("htmlLink"),
    }


def list_events(user_id, *, start, end, limit=20, query=None):
    if not get_status(user_id)["connected"]:
        raise RuntimeError("Google Calendar read access is not connected.")
    token = gmail_service._access_token(user_id)
    params = {
        "timeMin": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "timeMax": end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "singleEvents": "true", "orderBy": "startTime", "maxResults": max(1, min(int(limit), 50)),
        "timeZone": "America/Detroit",
    }
    if query:
        params["q"] = query[:200]
    response = requests.get(EVENTS_URL, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=15)
    response.raise_for_status()
    return [_event(item) for item in response.json().get("items") or [] if item.get("status") != "cancelled"]


def upcoming(user_id, days=7, limit=20):
    start = datetime.now(LOCAL_TIMEZONE)
    return list_events(user_id, start=start, end=start + timedelta(days=max(1, min(int(days), 31))), limit=limit)


def day_range(which):
    today = datetime.now(LOCAL_TIMEZONE).date()
    target = today + timedelta(days=1 if which == "tomorrow" else 0)
    start = datetime.combine(target, datetime.min.time(), LOCAL_TIMEZONE)
    return start, start + timedelta(days=1)
