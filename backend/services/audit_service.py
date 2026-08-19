import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from storage import connection


OUTCOMES = {"allowed", "denied", "succeeded", "failed"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def append_event(
    *,
    action: str,
    resource_type: str,
    outcome: str,
    actor_user_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    request_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if outcome not in OUTCOMES:
        raise ValueError("Unsupported audit outcome.")
    event = {
        "id": str(uuid.uuid4()),
        "actor_user_id": actor_user_id,
        "action": action.strip(),
        "resource_type": resource_type.strip(),
        "resource_id": resource_id,
        "outcome": outcome,
        "request_id": request_id,
        "details": details if isinstance(details, dict) else {},
        "created_utc": _utc_now(),
    }
    if not event["action"] or not event["resource_type"]:
        raise ValueError("Audit action and resource type are required.")
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO audit_events
                (id, actor_user_id, action, resource_type, resource_id, outcome,
                 request_id, details_json, created_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["id"],
                actor_user_id,
                event["action"],
                event["resource_type"],
                resource_id,
                outcome,
                request_id,
                json.dumps(event["details"], separators=(",", ":"), default=str),
                event["created_utc"],
            ),
        )
    return event


def list_events(limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 500))
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_events ORDER BY created_utc DESC, id DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
    events = []
    for row in rows:
        event = dict(row)
        event["details"] = json.loads(event.pop("details_json"))
        events.append(event)
    return events
