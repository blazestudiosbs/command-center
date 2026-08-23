import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from services import audit_service, discord_alert_service
from storage import connection, database_path


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _report_path():
    return database_path().parent / "infrastructure-agent-status.json"


def get_settings():
    with connection() as conn:
        row = conn.execute("SELECT * FROM infrastructure_agent_settings WHERE id = 'global'").fetchone()
    return {**dict(row), "security_updates_enabled": bool(row["security_updates_enabled"]), "health_checks_enabled": bool(row["health_checks_enabled"]), "automatic_reboot": False}


def set_settings(*, security_updates_enabled: bool, health_checks_enabled: bool):
    with connection() as conn:
        conn.execute(
            "UPDATE infrastructure_agent_settings SET security_updates_enabled = ?, health_checks_enabled = ?, automatic_reboot = 0, updated_utc = ? WHERE id = 'global'",
            (int(security_updates_enabled), int(health_checks_enabled), _now()),
        )
    return get_settings()


def get_status():
    try:
        report = json.loads(_report_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        report = {}
    return {
        "installed": bool(report), "settings": get_settings(),
        "health": report.get("health") or {"status": "not_installed", "issues": [], "checked_utc": None},
        "updates": report.get("updates") or {"status": "never_run", "reboot_performed": False},
        "report_path": str(_report_path()),
    }


def alert_on_new_issues():
    health = get_status()["health"]
    issues = health.get("issues") or []
    signature = hashlib.sha256(json.dumps(issues, sort_keys=True).encode()).hexdigest() if issues else "healthy"
    with connection() as conn:
        row = conn.execute("SELECT issue_signature FROM infrastructure_agent_alert_state WHERE id = 'global'").fetchone()
        previous = row["issue_signature"] if row else None
        conn.execute(
            "INSERT INTO infrastructure_agent_alert_state (id,issue_signature,updated_utc) VALUES ('global',?,?) ON CONFLICT(id) DO UPDATE SET issue_signature=excluded.issue_signature,updated_utc=excluded.updated_utc",
            (signature, _now()),
        )
    if signature == previous:
        return {"changed": False, "sent": False}
    if not issues:
        if previous and previous != "healthy":
            return {"changed": True, **discord_alert_service.send("Infrastructure recovered", "The latest host health check found no active infrastructure issues.", "success")}
        return {"changed": True, "sent": False}
    summary = "\n".join(f"- {item.get('detail', 'Unknown issue')}" for item in issues[:10])
    alert = discord_alert_service.send("Infrastructure issues detected", summary, "critical" if any(item.get("severity") == "critical" for item in issues) else "warning")
    audit_service.append_event(action="infrastructure.health_issues", resource_type="infrastructure_agent", resource_id="host", outcome="failed", details={"issues": issues, "alert_sent": alert.get("sent", False)})
    return {"changed": True, **alert}
