import hashlib
import json

from services import audit_service, discord_alert_service
from storage import connection, database_path


def get_settings():
    with connection() as conn:
        row = conn.execute("SELECT * FROM backup_agent_settings WHERE id = 'global'").fetchone()
    result = dict(row)
    result["enabled"] = bool(result["enabled"])
    return result


def set_enabled(enabled: bool):
    with connection() as conn:
        conn.execute(
            "UPDATE backup_agent_settings SET enabled = ?, updated_utc = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = 'global'",
            (int(enabled),),
        )
    return get_settings()


def get_status():
    path = database_path().parent / "backup-agent-status.json"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        report = {"status": "not_installed", "verified": False}
    safe_report = {key: value for key, value in report.items() if key != "error"}
    if report.get("error"):
        safe_report["detail"] = report["error"][:500]
    return {"installed": report.get("status") != "not_installed", "settings": get_settings(), "last_backup": safe_report}


def alert_on_change():
    report = get_status()["last_backup"]
    signature = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
    with connection() as conn:
        row = conn.execute("SELECT status_signature FROM backup_agent_alert_state WHERE id = 'global'").fetchone()
        previous = row["status_signature"] if row else None
        conn.execute(
            "INSERT INTO backup_agent_alert_state (id,status_signature,updated_utc) VALUES ('global',?,strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(id) DO UPDATE SET status_signature=excluded.status_signature,updated_utc=excluded.updated_utc",
            (signature,),
        )
    if signature == previous or report.get("status") in {"not_installed", "disabled", "never_run"}:
        return {"changed": signature != previous, "sent": False}
    if report.get("status") == "failed":
        alert = discord_alert_service.send("Command Center backup failed", report.get("detail", "The backup agent reported a failure."), "critical")
        audit_service.append_event(action="backup.failed", resource_type="backup_agent", resource_id="global", outcome="failed", details={"alert_sent": alert.get("sent", False)})
        return {"changed": True, **alert}
    return {"changed": True, "sent": False}
