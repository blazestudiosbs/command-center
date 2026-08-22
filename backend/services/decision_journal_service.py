import json
from typing import Any

from storage import connection


def _audit_entry(event: dict[str, Any]) -> dict[str, Any]:
    details = event.get("details") or {}
    action = event["action"]
    return {
        "id": f'audit:{event["id"]}',
        "kind": "route" if action == "conversation.route" else ("monitor" if action.startswith("service_monitor.") else "control"),
        "title": action.replace(".", " ").replace("_", " ").title(),
        "domain": "conversation" if action.startswith("conversation.") else ("infrastructure" if action.startswith("service_monitor.") else None),
        "provider": details.get("route") or details.get("provider"),
        "model": details.get("model"),
        "decision": event["outcome"],
        "reason": (
            details.get("reason")
            or details.get("detail")
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


def _source_records() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    with connection() as conn:
        audit_rows = conn.execute(
            """
            SELECT * FROM audit_events
            WHERE action LIKE 'conversation.%'
               OR action LIKE 'cloud_routing.%'
               OR action LIKE 'control.%'
               OR action LIKE 'permission.%'
               OR action LIKE 'home_assistant.%'
               OR action LIKE 'service_monitor.%'
            ORDER BY created_utc DESC, id DESC
            """
        ).fetchall()
        budget_rows = conn.execute(
            "SELECT * FROM budget_ledger ORDER BY created_utc DESC, id DESC"
        ).fetchall()
        route_rows = conn.execute(
            "SELECT * FROM routing_decisions ORDER BY created_utc DESC, id DESC"
        ).fetchall()
    audit = []
    for row in audit_rows:
        event = dict(row)
        event["details"] = json.loads(event.pop("details_json"))
        audit.append(event)
    return audit, [dict(row) for row in budget_rows], [dict(row) for row in route_rows]


def _group_audit_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    route_request_ids = {
        event["request_id"]
        for event in events
        if event["action"] == "conversation.route" and event.get("request_id")
    }
    return [
        _audit_entry(event)
        for event in events
        if not (
            event["action"] == "conversation.response"
            and event.get("request_id") in route_request_ids
        )
    ]


def get_page(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 100))
    safe_offset = max(0, int(offset))
    audit, budget, routes = _source_records()
    entries = sorted(
        _group_audit_events(audit)
        + [_budget_entry(entry) for entry in budget]
        + [_simulation_entry(entry) for entry in routes],
        key=lambda item: item["created_utc"],
        reverse=True,
    )
    summary = {
        "total_entries": len(entries),
        "local_routes": sum(
            entry["kind"] == "route" and entry["provider"] == "local" and entry["decision"] == "succeeded"
            for entry in entries
        ),
        "cloud_routes": sum(
            entry["kind"] == "route" and entry["provider"] == "openai" and entry["decision"] == "succeeded"
            for entry in entries
        ),
        "failures": sum(entry["decision"] == "failed" for entry in entries),
        "actual_cloud_cost_usd": round(
            sum(entry["actual_cost_usd"] or 0 for entry in entries if entry["kind"] == "cloud_request"),
            8,
        ),
    }
    page = entries[safe_offset:safe_offset + safe_limit]
    return {
        "entries": page,
        "summary": summary,
        "limit": safe_limit,
        "offset": safe_offset,
        "has_more": safe_offset + len(page) < len(entries),
    }


def list_entries(limit: int = 100) -> list[dict[str, Any]]:
    return get_page(limit=limit)["entries"]
