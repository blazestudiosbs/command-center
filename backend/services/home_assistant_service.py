import os
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from urllib.parse import urlparse

import requests

from storage import connection

ACTION_TTL_MINUTES = 10


def _now():
    return datetime.now(timezone.utc)


def _iso(value):
    return value.isoformat().replace("+00:00", "Z")


def _config() -> tuple[str | None, str | None]:
    url = os.getenv("HOME_ASSISTANT_URL", "").strip().rstrip("/")
    token = os.getenv("HOME_ASSISTANT_TOKEN", "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        url = ""
    return (url or None, token or None)


def get_status(*, check_connection: bool = False) -> dict:
    url, token = _config()
    configured = bool(url and token)
    result = {
        "provider": "home_assistant",
        "configured": configured,
        "status": "configured" if configured else "not_configured",
        "connection_status": "not_checked" if configured else "disabled",
        "detail": (
            "Home Assistant credentials are configured; connectivity has not been checked."
            if configured
            else "HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN are required."
        ),
    }
    if not configured or not check_connection:
        return result
    try:
        response = requests.get(
            f"{url}/api/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        response.raise_for_status()
        return {**result, "status": "online", "connection_status": "connected", "detail": "Home Assistant is reachable."}
    except requests.RequestException:
        return {**result, "status": "offline", "connection_status": "failed", "detail": "Home Assistant could not be reached."}


def get_overview(limit: int = 250) -> dict:
    url, token = _config()
    status = get_status(check_connection=True)
    if status["connection_status"] != "connected":
        return {"status": status, "entities": []}
    try:
        response = requests.get(
            f"{url}/api/states",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return {
            "status": {**status, "status": "offline", "connection_status": "failed", "detail": "Home Assistant states could not be read."},
            "entities": [],
        }
    entities = []
    for item in payload[:max(1, min(int(limit), 500))] if isinstance(payload, list) else []:
        attributes = item.get("attributes") if isinstance(item, dict) else {}
        attributes = attributes if isinstance(attributes, dict) else {}
        entity_id = str(item.get("entity_id", ""))
        if not entity_id:
            continue
        entities.append({
            "entity_id": entity_id,
            "domain": entity_id.partition(".")[0],
            "name": str(attributes.get("friendly_name") or entity_id),
            "state": str(item.get("state", "unknown")),
            "unit": attributes.get("unit_of_measurement"),
            "device_class": attributes.get("device_class"),
            "last_changed": item.get("last_changed"),
        })
    return {"status": status, "entities": entities}


def light_permissions(user_id):
    with connection() as conn:
        rows = conn.execute("SELECT entity_id,enabled FROM home_light_permissions WHERE user_id=?", (user_id,)).fetchall()
    return {row["entity_id"]: bool(row["enabled"]) for row in rows}


def set_light_permission(user_id, entity_id, enabled):
    if not entity_id.startswith("light."):
        raise ValueError("Only Home Assistant light entities can be approved.")
    now = _iso(_now())
    with connection() as conn:
        conn.execute("INSERT INTO home_light_permissions (user_id,entity_id,enabled,updated_utc) VALUES (?,?,?,?) ON CONFLICT(user_id,entity_id) DO UPDATE SET enabled=excluded.enabled,updated_utc=excluded.updated_utc", (user_id, entity_id, int(enabled), now))
    return {"entity_id": entity_id, "enabled": bool(enabled), "updated_utc": now}


def _entity(entity_id):
    url, token = _config()
    if not url or not token:
        raise RuntimeError("Home Assistant is not connected.")
    response = requests.get(f"{url}/api/states/{quote(entity_id, safe='')}", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    if response.status_code == 404:
        raise ValueError("That Home Assistant light was not found.")
    response.raise_for_status()
    item = response.json()
    return {"entity_id": item.get("entity_id"), "name": (item.get("attributes") or {}).get("friendly_name") or entity_id, "state": item.get("state", "unknown")}


def prepare_light_action(user_id, *, entity_id, action):
    if action not in {"turn_on", "turn_off"}:
        raise ValueError("Only turn on and turn off are supported.")
    if not entity_id.startswith("light.") or not light_permissions(user_id).get(entity_id, False):
        raise PermissionError("This light is not approved for Vera control.")
    entity = _entity(entity_id)
    if entity["entity_id"] != entity_id:
        raise ValueError("Home Assistant returned an unexpected entity.")
    now, action_id = _now(), str(uuid.uuid4())
    with connection() as conn:
        conn.execute("INSERT INTO home_light_action_requests (id,user_id,entity_id,action,entity_name,before_state,status,created_utc,expires_utc) VALUES (?,?,?,?,?,?,'pending',?,?)", (action_id, user_id, entity_id, action, entity["name"], entity["state"], _iso(now), _iso(now + timedelta(minutes=ACTION_TTL_MINUTES))))
    return {"id": action_id, "entity_id": entity_id, "entity_name": entity["name"], "action": action, "before_state": entity["state"], "status": "pending", "expires_utc": _iso(now + timedelta(minutes=ACTION_TTL_MINUTES))}


def pending_light_actions(user_id, limit=20):
    now = _iso(_now())
    with connection() as conn:
        conn.execute("UPDATE home_light_action_requests SET status='expired' WHERE user_id=? AND status='pending' AND expires_utc<=?", (user_id, now))
        rows = conn.execute("SELECT id,entity_id,entity_name,action,before_state,status,expires_utc FROM home_light_action_requests WHERE user_id=? AND status='pending' ORDER BY created_utc DESC LIMIT ?", (user_id, max(1, min(int(limit), 50)))).fetchall()
    return [dict(row) for row in rows]


def confirm_light_action(user_id, action_id):
    now = _now()
    with connection() as conn:
        row = conn.execute("SELECT * FROM home_light_action_requests WHERE id=? AND user_id=?", (action_id, user_id)).fetchone()
        if not row or row["status"] != "pending":
            raise ValueError("This light action is no longer pending.")
        if row["expires_utc"] <= _iso(now):
            conn.execute("UPDATE home_light_action_requests SET status='expired' WHERE id=?", (action_id,))
            raise ValueError("This light confirmation expired. Prepare it again.")
        if not light_permissions(user_id).get(row["entity_id"], False):
            raise PermissionError("This light is no longer approved for Vera control.")
        conn.execute("UPDATE home_light_action_requests SET status='executing' WHERE id=?", (action_id,))
    url, token = _config()
    try:
        response = requests.post(f"{url}/api/services/light/{row['action']}", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json={"entity_id": row["entity_id"]}, timeout=10)
        response.raise_for_status()
    except Exception:
        with connection() as conn:
            conn.execute("UPDATE home_light_action_requests SET status='failed',completed_utc=? WHERE id=?", (_iso(_now()), action_id))
        raise
    with connection() as conn:
        conn.execute("UPDATE home_light_action_requests SET status='completed',completed_utc=? WHERE id=?", (_iso(_now()), action_id))
    return {"id": action_id, "entity_id": row["entity_id"], "entity_name": row["entity_name"], "action": row["action"], "before_state": row["before_state"], "status": "completed"}
