import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from services import budget_service, policy_service
from storage import connection


DEFAULT_LOCAL_MODEL = "qwen3:4b-instruct"
DEFAULT_CLOUD_MODEL = "gpt-4.1-mini"
DEFAULT_LOCAL_CONFIDENCE_THRESHOLD = 0.70


class CloudRoutingVersionConflictError(RuntimeError):
    pass


class CloudRoutingUnavailableError(RuntimeError):
    pass


def _bounded_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if 0 <= value <= 1 else default


def get_config() -> dict[str, Any]:
    cloud_state = get_cloud_routing_state()
    return {
        "mode": "simulation",
        "strategy": "local_first",
        "local_model": os.getenv("VERA_LOCAL_MODEL", DEFAULT_LOCAL_MODEL).strip() or DEFAULT_LOCAL_MODEL,
        "cloud_model": os.getenv("OPENAI_MODEL", DEFAULT_CLOUD_MODEL).strip() or DEFAULT_CLOUD_MODEL,
        "local_confidence_threshold": _bounded_float(
            "VERA_ROUTER_LOCAL_CONFIDENCE_THRESHOLD", DEFAULT_LOCAL_CONFIDENCE_THRESHOLD
        ),
        "execution_enabled": False,
        "cloud_routing_enabled": cloud_state["enabled"],
    }


def get_cloud_routing_state() -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM cloud_routing_state WHERE id = 'global'"
        ).fetchone()
    if not row:
        raise RuntimeError("Cloud routing state is unavailable.")
    state = dict(row)
    state["enabled"] = bool(state["enabled"])
    state["effective_enabled"] = (
        state["enabled"] and policy_service.get_control_state()["mode"] == "active"
    )
    return state


def set_cloud_routing(
    *,
    enabled: bool,
    actor_user_id: Optional[str],
    reason: str,
    expected_version: Optional[int] = None,
) -> dict[str, Any]:
    cleaned_reason = reason.strip()[:500]
    if enabled and policy_service.get_control_state()["mode"] != "active":
        raise CloudRoutingUnavailableError(
            "Cloud routing can only be enabled while Vera autonomy is active."
        )
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            "SELECT * FROM cloud_routing_state WHERE id = 'global'"
        ).fetchone()
        if not current:
            raise RuntimeError("Cloud routing state is unavailable.")
        if expected_version is not None and current["version"] != expected_version:
            raise CloudRoutingVersionConflictError(
                "Cloud routing state changed; reload before retrying."
            )
        if bool(current["enabled"]) == bool(enabled):
            state = dict(current)
            state["enabled"] = bool(state["enabled"])
            state["effective_enabled"] = (
                state["enabled"] and policy_service.get_control_state()["mode"] == "active"
            )
            return state
        next_version = current["version"] + 1
        changed_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        conn.execute(
            """
            UPDATE cloud_routing_state
            SET enabled = ?, changed_by_user_id = ?, reason = ?, version = ?, changed_utc = ?
            WHERE id = 'global'
            """,
            (int(enabled), actor_user_id, cleaned_reason, next_version, changed_utc),
        )
        row = conn.execute(
            "SELECT * FROM cloud_routing_state WHERE id = 'global'"
        ).fetchone()
    state = dict(row)
    state["enabled"] = bool(state["enabled"])
    state["effective_enabled"] = (
        state["enabled"] and policy_service.get_control_state()["mode"] == "active"
    )
    return state


def cloud_routing_enabled() -> bool:
    return get_cloud_routing_state()["effective_enabled"]


def get_status() -> dict[str, Any]:
    config = get_config()
    with connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(CASE WHEN decision = 'local' THEN 1 ELSE 0 END), 0) AS local,
                   COALESCE(SUM(CASE WHEN decision = 'would_escalate' THEN 1 ELSE 0 END), 0) AS escalations,
                   COALESCE(SUM(CASE WHEN decision IN ('approval_required', 'blocked') THEN 1 ELSE 0 END), 0) AS blocked
            FROM routing_decisions
            """
        ).fetchone()
    return {
        **config,
        "cloud_routing": get_cloud_routing_state(),
        "decisions": {
            "total": int(row["total"]),
            "local": int(row["local"]),
            "would_escalate": int(row["escalations"]),
            "blocked_or_waiting": int(row["blocked"]),
        },
        "detail": "Route decisions remain simulated; the cloud toggle gates approved live API endpoints.",
    }


def _save(entry: dict[str, Any]) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO routing_decisions
                (id, mode, domain, local_model, local_available, local_confidence,
                 local_threshold, input_tokens, max_output_tokens, cloud_model,
                 estimated_cloud_cost_usd, decision, selected_provider, selected_model,
                 policy_effect, reason, cloud_call_made, created_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["id"], entry["mode"], entry["domain"], entry["local_model"],
                int(entry["local_available"]), entry["local_confidence"], entry["local_threshold"],
                entry["input_tokens"], entry["max_output_tokens"], entry["cloud_model"],
                entry["estimated_cloud_cost_usd"], entry["decision"], entry["selected_provider"],
                entry["selected_model"], entry["policy_effect"], entry["reason"], 0,
                entry["created_utc"],
            ),
        )


def simulate(
    *,
    domain: str,
    prompt: str,
    max_output_tokens: int,
    local_available: bool = True,
    local_confidence: float = 1.0,
    approved: bool = False,
) -> dict[str, Any]:
    config = get_config()
    normalized_domain = domain.strip().lower()
    confidence = min(1.0, max(0.0, float(local_confidence)))
    input_tokens = budget_service.estimate_input_tokens(prompt)
    estimated_cloud_cost = budget_service.estimate_cost(input_tokens, max_output_tokens)
    entry = {
        "id": str(uuid.uuid4()),
        "mode": "simulation",
        "domain": normalized_domain,
        "local_model": config["local_model"],
        "local_available": bool(local_available),
        "local_confidence": confidence,
        "local_threshold": config["local_confidence_threshold"],
        "input_tokens": input_tokens,
        "max_output_tokens": max(0, int(max_output_tokens)),
        "cloud_model": config["cloud_model"],
        "estimated_cloud_cost_usd": estimated_cloud_cost,
        "decision": "local",
        "selected_provider": "local",
        "selected_model": config["local_model"],
        "policy_effect": "allow",
        "reason": "The local model is available and meets the configured confidence threshold.",
        "cloud_call_made": False,
        "execution_performed": False,
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    local_policy = policy_service.evaluate_domain_request(
        domain=normalized_domain,
        provider="local",
        model=config["local_model"],
        estimated_cost_usd=0,
        approved=approved,
    )
    entry["local_policy"] = local_policy

    if local_available and confidence >= config["local_confidence_threshold"] and local_policy["allowed"]:
        _save(entry)
        return entry

    budget_simulation = budget_service.simulate(
        prompt=prompt,
        max_output_tokens=max_output_tokens,
        domain=normalized_domain,
        model=config["cloud_model"],
    )
    policy = policy_service.evaluate_domain_request(
        domain=normalized_domain,
        provider="openai",
        model=config["cloud_model"],
        estimated_cost_usd=estimated_cloud_cost,
        approved=approved,
    )
    entry["budget"] = budget_simulation
    entry["policy"] = policy
    entry["policy_effect"] = policy["effect"]

    if policy["allowed"]:
        entry.update(
            decision="would_escalate",
            selected_provider="openai",
            selected_model=config["cloud_model"],
            reason="Local capability was insufficient; policy and budget permit simulated cloud escalation.",
        )
    elif policy["effect"] == "approval_required":
        entry.update(
            decision="approval_required",
            selected_provider=None,
            selected_model=None,
            reason=policy["reason"],
        )
    elif local_available and local_policy["allowed"]:
        entry.update(
            decision="local_fallback",
            selected_provider="local",
            selected_model=config["local_model"],
            reason=f"Cloud escalation was denied; Vera would remain local. {policy['reason']}",
        )
    else:
        local_reason = (
            local_policy["reason"] if local_available else "The local model is unavailable."
        )
        entry.update(
            decision="blocked",
            selected_provider=None,
            selected_model=None,
            reason=(
                "No permitted route is available. "
                f"Local: {local_reason} Cloud: {policy['reason']}"
            ),
        )

    _save(entry)
    return entry


def list_decisions(limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 500))
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM routing_decisions ORDER BY created_utc DESC, id DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
    decisions = []
    for row in rows:
        decision = dict(row)
        decision["local_available"] = bool(decision["local_available"])
        decision["cloud_call_made"] = False
        decisions.append(decision)
    return decisions
