from typing import Any

from services import audit_service, budget_service, router_service


def _audit_entry(event: dict[str, Any]) -> dict[str, Any]:
    details = event.get("details") or {}
    action = event["action"]
    return {
        "id": f'audit:{event["id"]}',
        "kind": "route" if action == "conversation.route" else "control",
        "title": action.replace(".", " ").replace("_", " ").title(),
        "domain": "conversation" if action.startswith("conversation.") else None,
        "provider": details.get("route") or details.get("provider"),
        "model": details.get("model"),
        "decision": event["outcome"],
        "reason": (
            details.get("reason")
            or details.get("cloud_error_type")
            or details.get("error_type")
            or (f'Local fallback trigger: {details["local_error_type"]}' if details.get("local_error_type") else None)
        ),
        "estimated_cost_usd": None,
        "actual_cost_usd": None,
        "created_utc": event["created_utc"],
    }


def _budget_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f'budget:{entry["id"]}',
        "kind": "cloud_request" if entry["mode"] == "live" else "simulation",
        "title": "Cloud Request" if entry["mode"] == "live" else "Budget Simulation",
        "domain": entry["domain"],
        "provider": "openai" if entry["mode"] == "live" else None,
        "model": entry["model"],
        "decision": entry["decision"],
        "reason": entry["reason"],
        "estimated_cost_usd": entry["estimated_cost_usd"],
        "actual_cost_usd": entry["actual_cost_usd"],
        "created_utc": entry["created_utc"],
    }


def _simulation_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f'route:{entry["id"]}',
        "kind": "route_simulation",
        "title": "Route Simulation",
        "domain": entry["domain"],
        "provider": entry["selected_provider"],
        "model": entry["selected_model"],
        "decision": entry["decision"],
        "reason": entry["reason"],
        "estimated_cost_usd": entry["estimated_cloud_cost_usd"],
        "actual_cost_usd": None,
        "created_utc": entry["created_utc"],
    }


def list_entries(limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 200))
    audit = [
        _audit_entry(event)
        for event in audit_service.list_events(safe_limit)
        if event["action"].startswith(("conversation.", "cloud_routing.", "control.", "permission."))
    ]
    budget = [_budget_entry(entry) for entry in budget_service.list_ledger(safe_limit)]
    routes = [_simulation_entry(entry) for entry in router_service.list_decisions(safe_limit)]
    return sorted(audit + budget + routes, key=lambda item: item["created_utc"], reverse=True)[:safe_limit]
