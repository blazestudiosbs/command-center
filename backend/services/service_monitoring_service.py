import os
from datetime import datetime, timezone
from typing import Callable

import docker

from services import audit_service, discord_alert_service
from storage import connection


DEFAULT_CONTAINERS = (
    "command-center",
    "vera-discord",
    "vera-ollama",
    "minecraft-atm10",
    "plex",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def configured_containers() -> tuple[str, ...]:
    raw = os.getenv("VERA_MONITORED_CONTAINERS", "").strip()
    values = [item.strip() for item in raw.split(",")] if raw else list(DEFAULT_CONTAINERS)
    return tuple(dict.fromkeys(item for item in values if item))


def interval_seconds() -> int:
    try:
        return max(15, int(os.getenv("VERA_MONITOR_INTERVAL_SECONDS", "60")))
    except ValueError:
        return 60


def cooldown_seconds() -> int:
    try:
        return max(0, int(os.getenv("VERA_MONITOR_ALERT_COOLDOWN_SECONDS", "300")))
    except ValueError:
        return 300


def get_notification_preferences() -> dict:
    names = configured_containers()
    with connection() as conn:
        global_row = conn.execute(
            "SELECT * FROM monitoring_notification_settings WHERE id = 'global'"
        ).fetchone()
        if global_row is None:
            now = _utc_now()
            conn.execute(
                """
                INSERT INTO monitoring_notification_settings (id, alerts_enabled, cooldown_seconds, updated_utc)
                VALUES ('global', 1, ?, ?)
                """,
                (cooldown_seconds(), now),
            )
            global_row = {"alerts_enabled": 1, "cooldown_seconds": cooldown_seconds(), "updated_utc": now}
        service_rows = conn.execute(
            "SELECT * FROM monitoring_service_notification_preferences"
        ).fetchall()
    stored = {row["container_name"]: dict(row) for row in service_rows}
    return {
        "alerts_enabled": bool(global_row["alerts_enabled"]),
        "cooldown_seconds": global_row["cooldown_seconds"],
        "services": [
            {
                "container_name": name,
                "display_name": _display_name(name),
                "outage_alerts_enabled": bool(stored.get(name, {}).get("outage_alerts_enabled", 1)),
                "recovery_alerts_enabled": bool(stored.get(name, {}).get("recovery_alerts_enabled", 1)),
            }
            for name in names
        ],
    }


def set_notification_preferences(
    *, alerts_enabled: bool, cooldown: int, services: list[dict]
) -> dict:
    known = set(configured_containers())
    supplied = {item["container_name"] for item in services}
    if not supplied.issubset(known):
        raise ValueError("Notification preferences contain an unknown service.")
    now = _utc_now()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO monitoring_notification_settings (id, alerts_enabled, cooldown_seconds, updated_utc)
            VALUES ('global', ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                alerts_enabled = excluded.alerts_enabled,
                cooldown_seconds = excluded.cooldown_seconds,
                updated_utc = excluded.updated_utc
            """,
            (int(alerts_enabled), cooldown, now),
        )
        for item in services:
            conn.execute(
                """
                INSERT INTO monitoring_service_notification_preferences
                    (container_name, outage_alerts_enabled, recovery_alerts_enabled, updated_utc)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(container_name) DO UPDATE SET
                    outage_alerts_enabled = excluded.outage_alerts_enabled,
                    recovery_alerts_enabled = excluded.recovery_alerts_enabled,
                    updated_utc = excluded.updated_utc
                """,
                (
                    item["container_name"],
                    int(item["outage_alerts_enabled"]),
                    int(item["recovery_alerts_enabled"]),
                    now,
                ),
            )
    return get_notification_preferences()


def _display_name(container_name: str) -> str:
    names = {
        "command-center": "Command Center",
        "vera-discord": "Vera Discord",
        "vera-ollama": "Vera Ollama",
        "minecraft-atm10": "Minecraft",
        "plex": "Plex",
    }
    return names.get(container_name, container_name.replace("-", " ").title())


def docker_snapshot() -> dict[str, dict[str, str]]:
    client = docker.from_env()
    try:
        containers = {container.name: container for container in client.containers.list(all=True)}
        result = {}
        for name in configured_containers():
            container = containers.get(name)
            if container is None:
                result[name] = {"status": "missing", "detail": "Container was not found."}
            else:
                status = "running" if container.status == "running" else "stopped"
                result[name] = {"status": status, "detail": f"Docker status: {container.status}."}
        return result
    finally:
        client.close()


def record_snapshot(
    snapshot: dict[str, dict[str, str]],
    *,
    now: str | None = None,
    notifier: Callable[[str, str, str], dict] | None = None,
) -> list[dict]:
    checked_utc = now or _utc_now()
    notify = notifier or discord_alert_service.send
    preferences = get_notification_preferences()
    service_preferences = {item["container_name"]: item for item in preferences["services"]}
    transitions = []

    for container_name in configured_containers():
        observation = snapshot.get(container_name, {"status": "missing", "detail": "Container was not found."})
        status = observation.get("status", "unknown")
        detail = observation.get("detail", "")
        display_name = _display_name(container_name)
        with connection() as conn:
            previous = conn.execute(
                "SELECT * FROM service_monitor_state WHERE container_name = ?",
                (container_name,),
            ).fetchone()
            if previous is None:
                conn.execute(
                    """
                    INSERT INTO service_monitor_state
                        (container_name, display_name, status, detail, last_checked_utc, last_changed_utc)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (container_name, display_name, status, detail, checked_utc, checked_utc),
                )
                continue
            if previous["status"] == status:
                conn.execute(
                    "UPDATE service_monitor_state SET detail = ?, last_checked_utc = ? WHERE container_name = ?",
                    (detail, checked_utc, container_name),
                )
                continue

            last_alerted = _parse_utc(previous["last_alerted_utc"])
            checked = _parse_utc(checked_utc)
            is_recovery = status == "running"
            service_preference = service_preferences[container_name]
            transition_enabled = (
                service_preference["recovery_alerts_enabled"] if is_recovery
                else service_preference["outage_alerts_enabled"]
            )
            cooldown_elapsed = not last_alerted or not checked or (checked - last_alerted).total_seconds() >= preferences["cooldown_seconds"]
            alert_allowed = preferences["alerts_enabled"] and transition_enabled and cooldown_elapsed
            action = "service_monitor.recovery" if status == "running" else "service_monitor.outage"
            outcome = "succeeded" if status == "running" else "failed"
            transition = {
                "container_name": container_name,
                "display_name": display_name,
                "from_status": previous["status"],
                "to_status": status,
                "detail": detail,
                "created_utc": checked_utc,
                "alert_sent": False,
                "alert_suppressed": None,
            }
            if not preferences["alerts_enabled"]:
                transition["alert_suppressed"] = "alerts_disabled"
            elif not transition_enabled:
                transition["alert_suppressed"] = "service_preference"
            elif not cooldown_elapsed:
                transition["alert_suppressed"] = "cooldown"
            if alert_allowed:
                severity = "success" if status == "running" else "critical"
                title = f"{display_name} recovered" if status == "running" else f"{display_name} is unavailable"
                alert = notify(title, f"State changed from {previous['status']} to {status}. {detail}", severity)
                transition["alert_sent"] = bool(alert.get("sent"))
                transition["alert_error"] = alert.get("error")
                if alert.get("sent"):
                    transition["last_alerted_utc"] = checked_utc

            conn.execute(
                """
                UPDATE service_monitor_state
                SET display_name = ?, status = ?, detail = ?, last_checked_utc = ?,
                    last_changed_utc = ?, last_alerted_utc = COALESCE(?, last_alerted_utc)
                WHERE container_name = ?
                """,
                (display_name, status, detail, checked_utc, checked_utc, transition.get("last_alerted_utc"), container_name),
            )
        audit_service.append_event(
            action=action,
            resource_type="docker_container",
            resource_id=container_name,
            outcome=outcome,
            details=transition,
        )
        transitions.append(transition)
    return transitions


def check_once() -> list[dict]:
    return record_snapshot(docker_snapshot())


def get_status() -> dict:
    names = configured_containers()
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM service_monitor_state ORDER BY display_name"
        ).fetchall()
    stored = {row["container_name"]: dict(row) for row in rows}
    services = [
        stored.get(name) or {
            "container_name": name,
            "display_name": _display_name(name),
            "status": "pending",
            "detail": "Waiting for the first monitoring check.",
            "last_checked_utc": None,
            "last_changed_utc": None,
            "last_alerted_utc": None,
        }
        for name in names
    ]
    healthy = sum(service["status"] == "running" for service in services)
    preferences = get_notification_preferences()
    return {
        "mode": "observation_only",
        "automatic_restarts": False,
        "interval_seconds": interval_seconds(),
        "alert_cooldown_seconds": preferences["cooldown_seconds"],
        "alerts_enabled": preferences["alerts_enabled"],
        "discord_alerts_configured": bool(os.getenv("DISCORD_WEBHOOK", "").strip()),
        "summary": {
            "total": len(services),
            "healthy": healthy,
            "unavailable": sum(service["status"] in {"stopped", "missing"} for service in services),
            "pending": sum(service["status"] == "pending" for service in services),
        },
        "services": services,
    }
