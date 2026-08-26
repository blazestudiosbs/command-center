import json
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from services import agent_permission_service, backup_service, calendar_service, discord_alert_service, gmail_service, infrastructure_service, release_service, service_monitoring_service
from storage import connection

LOCAL_TIMEZONE = ZoneInfo("America/Detroit")


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_settings(user_id):
    with connection() as conn:
        row = conn.execute("SELECT * FROM daily_briefing_settings WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            conn.execute("INSERT INTO daily_briefing_settings (user_id,enabled,delivery_time,timezone,updated_utc) VALUES (?,0,'07:00','America/Detroit',?)", (user_id, _utc_now()))
            row = conn.execute("SELECT * FROM daily_briefing_settings WHERE user_id=?", (user_id,)).fetchone()
    result = dict(row)
    for key in ("enabled", "include_calendar", "include_gmail", "include_infrastructure", "include_backups", "include_approvals"):
        result[key] = bool(result[key])
    return result


def set_settings(user_id, **values):
    delivery_time = values["delivery_time"]
    try:
        datetime.strptime(delivery_time, "%H:%M")
    except ValueError as exc:
        raise ValueError("Delivery time must use HH:MM.") from exc
    fields = ("enabled", "include_calendar", "include_gmail", "include_infrastructure", "include_backups", "include_approvals")
    parameters = [int(bool(values[field])) for field in fields[:1]]
    parameters.append(delivery_time)
    parameters.extend(int(bool(values[field])) for field in fields[1:])
    parameters.extend((_utc_now(), user_id))
    with connection() as conn:
        conn.execute("UPDATE daily_briefing_settings SET enabled=?,delivery_time=?,include_calendar=?,include_gmail=?,include_infrastructure=?,include_backups=?,include_approvals=?,updated_utc=? WHERE user_id=?", parameters)
    return get_settings(user_id)


def _calendar_section(user_id):
    if not agent_permission_service.is_allowed(user_id, "calendar", "read_events") or not calendar_service.get_status(user_id)["connected"]:
        return {"status": "unavailable", "items": []}
    start, end = calendar_service.day_range("today")
    return {"status": "ready", "items": calendar_service.list_events(user_id, start=start, end=end, limit=10)}


def _gmail_section(user_id):
    if not agent_permission_service.is_allowed(user_id, "gmail", "read_inbox") or not gmail_service.get_status(user_id)["connected"]:
        return {"status": "unavailable", "items": []}
    items = gmail_service.search_metadata(user_id, "is:unread newer_than:2d", limit=5)
    return {"status": "ready", "items": [{"sender": item["sender"], "subject": item["subject"]} for item in items]}


def generate(user_id):
    agent_permission_service.require(user_id, "daily_briefing", "generate")
    settings = get_settings(user_id)
    sections = {}
    if settings["include_calendar"]:
        sections["calendar"] = _calendar_section(user_id)
    if settings["include_gmail"]:
        sections["gmail"] = _gmail_section(user_id)
    if settings["include_infrastructure"]:
        infrastructure = infrastructure_service.get_status()
        sections["infrastructure"] = {"host": infrastructure.get("health") or {}, "services": service_monitoring_service.get_status()["summary"]}
    if settings["include_backups"]:
        sections["backup"] = backup_service.get_status().get("last_backup")
    if settings["include_approvals"]:
        pending_releases = [item for item in release_service.list_releases(user_id) if item["status"] == "pending"]
        sections["approvals"] = {"pending_releases": len(pending_releases), "pending_calendar_changes": len(calendar_service.pending_changes(user_id))}
    return {"generated_utc": _utc_now(), "timezone": "America/Detroit", "cloud_processing": False, "read_only": True, "sections": sections}


def format_message(briefing):
    sections, lines = briefing["sections"], []
    calendar = sections.get("calendar")
    if calendar:
        lines.append(f"**Calendar:** {len(calendar['items'])} event(s) today" if calendar["status"] == "ready" else "**Calendar:** unavailable")
        for event in calendar["items"][:5]:
            when = "All day" if event["all_day"] else datetime.fromisoformat(event["start"].replace("Z", "+00:00")).astimezone(LOCAL_TIMEZONE).strftime("%-I:%M %p")
            lines.append(f"- {when} — {event['title']}")
    gmail = sections.get("gmail")
    if gmail:
        lines.append(f"**Gmail:** {len(gmail['items'])} recent unread message(s)" if gmail["status"] == "ready" else "**Gmail:** unavailable or permission off")
        for item in gmail["items"][:3]:
            lines.append(f"- {item['subject']} — {item['sender']}")
    infrastructure = sections.get("infrastructure")
    if infrastructure:
        issues = infrastructure["host"].get("issues") or []
        services = infrastructure["services"]
        lines.append(f"**Systems:** {services['healthy']}/{services['total']} services healthy; {len(issues)} host issue(s)")
    backup = sections.get("backup")
    if backup is not None:
        lines.append(f"**Backup:** {backup.get('status', 'unknown').replace('_', ' ')}" + (" · verified" if backup.get("verified") else ""))
    approvals = sections.get("approvals")
    if approvals:
        lines.append(f"**Approvals:** {approvals['pending_releases']} release(s), {approvals['pending_calendar_changes']} calendar change(s)")
    return "\n".join(lines)[:1750]


def run(user_id, *, mode="manual", local_date=None):
    briefing = generate(user_id)
    result = discord_alert_service.send("Vera Daily Briefing", format_message(briefing), "info")
    status = "sent" if result.get("sent") else "failed"
    now = _utc_now()
    with connection() as conn:
        conn.execute("INSERT INTO daily_briefing_runs (id,user_id,mode,status,summary_json,created_utc,sent_utc) VALUES (?,?,?,?,?,?,?)", (str(uuid.uuid4()), user_id, mode, status, json.dumps(briefing), now, now if status == "sent" else None))
        if mode == "scheduled":
            local_date = local_date or datetime.now(LOCAL_TIMEZONE).date().isoformat()
            conn.execute(
                "UPDATE daily_briefing_settings SET last_attempt_local_date=?,last_sent_local_date=CASE WHEN ?='sent' THEN ? ELSE last_sent_local_date END,updated_utc=? WHERE user_id=?",
                (local_date, status, local_date, now, user_id),
            )
    return {"status": status, "delivery": result, "briefing": briefing, "message": format_message(briefing)}


def run_if_due(user_id, now=None):
    local_now = (now or datetime.now(LOCAL_TIMEZONE)).astimezone(LOCAL_TIMEZONE)
    settings = get_settings(user_id)
    today = local_now.date().isoformat()
    if not settings["enabled"] or settings["last_attempt_local_date"] == today or local_now.strftime("%H:%M") < settings["delivery_time"]:
        return {"status": "skipped"}
    if not agent_permission_service.is_allowed(user_id, "daily_briefing", "scheduled_delivery"):
        return {"status": "skipped", "reason": "Scheduled delivery permission is off."}
    return run(user_id, mode="scheduled", local_date=today)
