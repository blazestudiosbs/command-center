import json
import uuid
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

from services import gmail_service
from storage import connection

EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
LOCAL_TIMEZONE = ZoneInfo("America/Detroit")
CHANGE_TTL_MINUTES = 15


def _utc_now():
    return datetime.now(timezone.utc)


def _iso(value):
    return value.isoformat().replace("+00:00", "Z")


def get_status(user_id):
    gmail = gmail_service.get_status(user_id)
    scopes = gmail.get("scopes") or []
    write_authorized = gmail_service.CALENDAR_EVENTS_SCOPE in scopes
    read_authorized = write_authorized or gmail_service.CALENDAR_READONLY_SCOPE in scopes
    return {
        "provider": "google_calendar", "configured": gmail["configured"],
        "connected": gmail["connected"] and read_authorized, "authorized": read_authorized,
        "write_authorized": write_authorized, "account": gmail.get("email_address"),
        "access": "create_and_edit" if write_authorized else "read_only",
        "can_create": write_authorized, "can_edit": write_authorized, "can_delete": write_authorized,
        "detail": ("Google Calendar is connected for confirmed creation and editing." if write_authorized else "Google Calendar is connected with read-only access." if read_authorized else "Authorize Google Calendar access."),
    }


def authorization_url(user_id, *, write=False):
    return gmail_service.authorization_url(user_id, calendar_read=not write, calendar_write=write)


def _event(item):
    start, end = item.get("start") or {}, item.get("end") or {}
    return {
        "id": item.get("id"), "title": item.get("summary") or "Busy",
        "start": start.get("dateTime") or start.get("date"), "end": end.get("dateTime") or end.get("date"),
        "all_day": "date" in start, "location": item.get("location"),
        "status": item.get("status"), "html_url": item.get("htmlLink"),
    }


def _headers(user_id):
    return {"Authorization": f"Bearer {gmail_service._access_token(user_id)}"}


def list_events(user_id, *, start, end, limit=20, query=None):
    if not get_status(user_id)["connected"]:
        raise RuntimeError("Google Calendar read access is not connected.")
    params = {
        "timeMin": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "timeMax": end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "singleEvents": "true", "orderBy": "startTime", "maxResults": max(1, min(int(limit), 50)), "timeZone": "America/Detroit",
    }
    if query:
        params["q"] = query[:200]
    response = requests.get(EVENTS_URL, headers=_headers(user_id), params=params, timeout=15)
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


def _normalized_change(*, title, start, end, location=None, all_day=False):
    title, location = (title or "").strip(), (location or "").strip()
    if not title:
        raise ValueError("Event title is required.")
    if not start or not end:
        raise ValueError("Event start and end are required.")
    if all_day:
        start_value, end_value = date.fromisoformat(start), date.fromisoformat(end)
    else:
        start_value, end_value = datetime.fromisoformat(start), datetime.fromisoformat(end)
        if start_value.tzinfo is None:
            start_value = start_value.replace(tzinfo=LOCAL_TIMEZONE)
        if end_value.tzinfo is None:
            end_value = end_value.replace(tzinfo=LOCAL_TIMEZONE)
    if end_value <= start_value:
        raise ValueError("Event end must be after its start.")
    return {"title": title[:300], "start": start_value.isoformat(), "end": end_value.isoformat(), "all_day": bool(all_day), "location": location[:500] or None}


def _google_body(change):
    key = "date" if change["all_day"] else "dateTime"
    body = {"summary": change["title"], "start": {key: change["start"]}, "end": {key: change["end"]}, "location": change.get("location") or ""}
    if not change["all_day"]:
        body["start"]["timeZone"] = body["end"]["timeZone"] = "America/Detroit"
    return body


def _get_google_event(user_id, event_id):
    response = requests.get(f"{EVENTS_URL}/{quote(event_id, safe='')}", headers=_headers(user_id), timeout=15)
    response.raise_for_status()
    return response.json()


def prepare_change(user_id, *, action, event_id=None, **fields):
    if action not in {"create", "edit", "delete"}:
        raise ValueError("Unsupported calendar action.")
    if not get_status(user_id)["write_authorized"]:
        raise RuntimeError("Authorize Calendar creation and editing with Google first.")
    desired = None if action == "delete" else _normalized_change(**fields)
    before, etag = None, None
    if action in {"edit", "delete"}:
        if not event_id:
            raise ValueError("Choose an event to edit.")
        source = _get_google_event(user_id, event_id)
        if source.get("status") == "cancelled":
            raise ValueError("This event has been cancelled.")
        before, etag = _event(source), source.get("etag")
    now, change_id = _utc_now(), str(uuid.uuid4())
    payload = {"before": before, "after": desired}
    with connection() as conn:
        conn.execute("INSERT INTO calendar_change_requests (id,user_id,action,event_id,event_etag,payload_json,status,created_utc,expires_utc) VALUES (?,?,?,?,?,?,'pending',?,?)", (change_id, user_id, action, event_id, etag, json.dumps(payload), _iso(now), _iso(now + timedelta(minutes=CHANGE_TTL_MINUTES))))
    return {"id": change_id, "action": action, "status": "pending", "expires_utc": _iso(now + timedelta(minutes=CHANGE_TTL_MINUTES)), **payload}


def pending_change_action(user_id, change_id):
    with connection() as conn:
        row = conn.execute("SELECT action FROM calendar_change_requests WHERE id = ? AND user_id = ? AND status = 'pending'", (change_id, user_id)).fetchone()
    if not row:
        raise ValueError("Calendar change not found or no longer pending.")
    return row["action"]


def pending_changes(user_id, limit=20):
    now = _iso(_utc_now())
    with connection() as conn:
        conn.execute("UPDATE calendar_change_requests SET status = 'expired' WHERE user_id = ? AND status = 'pending' AND expires_utc <= ?", (user_id, now))
        rows = conn.execute("SELECT id,action,payload_json,expires_utc FROM calendar_change_requests WHERE user_id = ? AND status = 'pending' ORDER BY created_utc DESC LIMIT ?", (user_id, max(1, min(int(limit), 50)))).fetchall()
    return [{"id": row["id"], "action": row["action"], "status": "pending", "expires_utc": row["expires_utc"], **json.loads(row["payload_json"])} for row in rows]


def confirm_change(user_id, change_id):
    now = _utc_now()
    with connection() as conn:
        row = conn.execute("SELECT * FROM calendar_change_requests WHERE id = ? AND user_id = ?", (change_id, user_id)).fetchone()
        if not row or row["status"] != "pending":
            raise ValueError("This calendar change is no longer pending.")
        if row["expires_utc"] <= _iso(now):
            conn.execute("UPDATE calendar_change_requests SET status = 'expired' WHERE id = ?", (change_id,))
            raise ValueError("This calendar confirmation expired. Prepare it again.")
        conn.execute("UPDATE calendar_change_requests SET status = 'executing' WHERE id = ?", (change_id,))
    payload, headers = json.loads(row["payload_json"]), {**_headers(user_id), "Content-Type": "application/json"}
    try:
        if row["action"] == "create":
            response = requests.post(EVENTS_URL, headers=headers, params={"sendUpdates": "none"}, json=_google_body(payload["after"]), timeout=15)
        elif row["action"] == "edit":
            if row["event_etag"]:
                headers["If-Match"] = row["event_etag"]
            response = requests.patch(f"{EVENTS_URL}/{quote(row['event_id'], safe='')}", headers=headers, params={"sendUpdates": "none"}, json=_google_body(payload["after"]), timeout=15)
        else:
            if row["event_etag"]:
                headers["If-Match"] = row["event_etag"]
            response = requests.delete(f"{EVENTS_URL}/{quote(row['event_id'], safe='')}", headers=headers, params={"sendUpdates": "none"}, timeout=15)
        response.raise_for_status()
    except Exception:
        with connection() as conn:
            conn.execute("UPDATE calendar_change_requests SET status = 'failed', completed_utc = ? WHERE id = ?", (_iso(_utc_now()), change_id))
        raise
    completed = payload["before"] if row["action"] == "delete" else _event(response.json())
    if row["action"] == "delete":
        completed = {**completed, "status": "deleted"}
    with connection() as conn:
        conn.execute("UPDATE calendar_change_requests SET status = 'completed', completed_utc = ? WHERE id = ?", (_iso(_utc_now()), change_id))
    return {"id": change_id, "action": row["action"], "status": "completed", "event": completed}
