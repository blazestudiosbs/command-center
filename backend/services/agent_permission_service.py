from datetime import datetime, timezone

from storage import connection


AGENTS = (
    {
        "id": "vera_conversation",
        "name": "Vera Conversation",
        "description": "Answers Bruce through connected conversation channels.",
        "capabilities": (
            {"id": "conversation", "name": "Answer conversations", "default": True, "available": True},
            {"id": "cloud_fallback", "name": "Use cloud fallback", "default": True, "available": True},
        ),
    },
    {
        "id": "gmail",
        "name": "Gmail Agent",
        "description": "Reads and summarizes the connected Gmail account.",
        "capabilities": (
            {"id": "read_inbox", "name": "Read inbox", "default": False, "available": True},
            {"id": "search", "name": "Search email", "default": False, "available": True},
            {"id": "organize_and_file", "name": "Organize and remove from Inbox", "default": False, "available": True},
            {"id": "permanent_delete", "name": "Run approved permanent-delete rules", "default": False, "available": True},
            {"id": "cloud_processing", "name": "Send uncertain sender/subject to cloud AI", "default": False, "available": True},
            {"id": "send", "name": "Send email", "default": False, "available": False},
            {"id": "modify", "name": "Modify or delete email", "default": False, "available": False},
        ),
    },
    {
        "id": "calendar",
        "name": "Calendar Agent",
        "description": "Reads events and makes explicitly confirmed Google Calendar changes.",
        "capabilities": (
            {"id": "read_events", "name": "Read event titles and times", "default": False, "available": True},
            {"id": "search", "name": "Search upcoming events", "default": False, "available": True},
            {"id": "create", "name": "Create confirmed events", "default": False, "available": True},
            {"id": "edit", "name": "Edit confirmed events", "default": False, "available": True},
            {"id": "delete", "name": "Delete events", "default": False, "available": False},
        ),
    },
    {
        "id": "service_monitor",
        "name": "Service Monitor",
        "description": "Observes Docker services and records state changes.",
        "capabilities": (
            {"id": "background_checks", "name": "Run background checks", "default": True, "available": True},
            {"id": "manual_checks", "name": "Allow Check now", "default": True, "available": True},
            {"id": "discord_alerts", "name": "Send Discord alerts", "default": True, "available": True},
            {"id": "restart_services", "name": "Restart services", "default": False, "available": False},
        ),
    },
    {
        "id": "development_worker",
        "name": "Development Worker",
        "description": "Runs explicitly approved development tasks.",
        "capabilities": (
            {"id": "manual_tasks", "name": "Run manual tasks", "default": True, "available": True},
            {"id": "autonomous_tasks", "name": "Run autonomous tasks", "default": False, "available": False},
        ),
    },
)


class AgentPermissionDeniedError(PermissionError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _definition(agent_id: str) -> dict | None:
    return next((agent for agent in AGENTS if agent["id"] == agent_id), None)


def _capability(agent: dict, capability: str) -> dict | None:
    return next((item for item in agent["capabilities"] if item["id"] == capability), None)


def _stored(user_id: str) -> dict[tuple[str, str], bool]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT agent_id, capability, enabled FROM agent_permissions WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return {(row["agent_id"], row["capability"]): bool(row["enabled"]) for row in rows}


def list_agents(user_id: str) -> list[dict]:
    stored = _stored(user_id)
    result = []
    for agent in AGENTS:
        enabled = stored.get((agent["id"], "enabled"), True)
        result.append(
            {
                "id": agent["id"],
                "name": agent["name"],
                "description": agent["description"],
                "enabled": enabled,
                "capabilities": [
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "enabled": stored.get((agent["id"], item["id"]), item["default"]),
                        "available": item["available"],
                    }
                    for item in agent["capabilities"]
                ],
            }
        )
    return result


def set_permission(*, user_id: str, agent_id: str, capability: str, enabled: bool) -> dict:
    agent = _definition(agent_id)
    if not agent:
        raise ValueError("Unknown agent.")
    if capability != "enabled":
        item = _capability(agent, capability)
        if not item:
            raise ValueError("Unknown agent capability.")
        if not item["available"]:
            raise ValueError("This capability is not available and remains locked off.")
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO agent_permissions (user_id, agent_id, capability, enabled, updated_utc)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, agent_id, capability) DO UPDATE SET
                enabled = excluded.enabled,
                updated_utc = excluded.updated_utc
            """,
            (user_id, agent_id, capability, int(enabled), _utc_now()),
        )
    return next(agent for agent in list_agents(user_id) if agent["id"] == agent_id)


def is_allowed(user_id: str, agent_id: str, capability: str) -> bool:
    agent = next((item for item in list_agents(user_id) if item["id"] == agent_id), None)
    if not agent or not agent["enabled"]:
        return False
    item = next((entry for entry in agent["capabilities"] if entry["id"] == capability), None)
    return bool(item and item["available"] and item["enabled"])


def require(user_id: str, agent_id: str, capability: str) -> None:
    if not is_allowed(user_id, agent_id, capability):
        raise AgentPermissionDeniedError(f"{agent_id} does not have permission for {capability}.")
