import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from services import budget_service
from storage import connection


CONTROL_MODES = {"active", "paused", "emergency_stop"}
READ_CAPABILITIES = {"conversation", "read"}
AUTONOMOUS_CAPABILITIES = {"autonomous_write", "agent_execute", "external_side_effect"}


class PolicyDeniedError(PermissionError):
    def __init__(self, decision: "PolicyDecision"):
        super().__init__(decision.reason)
        self.decision = decision


class ControlVersionConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    capability: str
    domain: str
    mode: str
    effect: str
    reason: str
    permission_id: Optional[str] = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_control_state() -> dict:
    with connection() as conn:
        row = conn.execute("SELECT * FROM control_state WHERE id = 'global'").fetchone()
    if not row:
        raise RuntimeError("Global control state is unavailable.")
    return dict(row)


def set_control_mode(
    *,
    mode: str,
    actor_user_id: str,
    reason: str,
    expected_version: Optional[int] = None,
) -> dict:
    if mode not in CONTROL_MODES:
        raise ValueError("Unsupported control mode.")
    cleaned_reason = reason.strip()[:500]
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT * FROM control_state WHERE id = 'global'").fetchone()
        if not current:
            raise RuntimeError("Global control state is unavailable.")
        if expected_version is not None and current["version"] != expected_version:
            raise ControlVersionConflictError("Control state changed; reload before retrying.")
        if current["mode"] == mode:
            return dict(current)
        next_version = current["version"] + 1
        changed_utc = _utc_now()
        conn.execute(
            """
            UPDATE control_state
            SET mode = ?, changed_by_user_id = ?, reason = ?, version = ?, changed_utc = ?
            WHERE id = 'global'
            """,
            (mode, actor_user_id, cleaned_reason, next_version, changed_utc),
        )
        row = conn.execute("SELECT * FROM control_state WHERE id = 'global'").fetchone()
    return dict(row)


def set_permission(
    *, user_id: str, domain: str, capability: str, effect: str
) -> dict:
    if effect not in {"allow", "deny", "approval_required"}:
        raise ValueError("Unsupported permission effect.")
    cleaned_domain = domain.strip().lower()
    cleaned_capability = capability.strip().lower()
    if not cleaned_domain or not cleaned_capability:
        raise ValueError("Permission domain and capability are required.")
    now = _utc_now()
    permission_id = str(uuid.uuid4())
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO permissions
                (id, user_id, domain, capability, effect, created_utc, updated_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, domain, capability) DO UPDATE SET
                effect = excluded.effect,
                updated_utc = excluded.updated_utc
            """,
            (permission_id, user_id, cleaned_domain, cleaned_capability, effect, now, now),
        )
        row = conn.execute(
            """
            SELECT * FROM permissions
            WHERE user_id = ? AND domain = ? AND capability = ?
            """,
            (user_id, cleaned_domain, cleaned_capability),
        ).fetchone()
    return dict(row)


def list_permissions(user_id: str) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM permissions WHERE user_id = ? ORDER BY domain, capability",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _domain_policy(row) -> dict[str, Any]:
    policy = dict(row)
    policy["allowed_models"] = json.loads(policy.pop("allowed_models_json"))
    policy["cloud_allowed"] = bool(policy["cloud_allowed"])
    policy["approval_required"] = bool(policy["approval_required"])
    return policy


def list_domain_policies() -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM domain_policies ORDER BY domain"
        ).fetchall()
    return [_domain_policy(row) for row in rows]


def get_domain_policy(domain: str) -> Optional[dict[str, Any]]:
    normalized_domain = domain.strip().lower()
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM domain_policies WHERE domain = ?",
            (normalized_domain,),
        ).fetchone()
    return _domain_policy(row) if row else None


def evaluate_domain_request(
    *,
    domain: str,
    provider: str,
    model: str,
    estimated_cost_usd: float,
    approved: bool = False,
) -> dict[str, Any]:
    normalized_domain = domain.strip().lower()
    normalized_provider = provider.strip().lower()
    normalized_model = model.strip()
    policy = get_domain_policy(normalized_domain)
    base = {
        "mode": "simulation",
        "domain": normalized_domain,
        "provider": normalized_provider,
        "model": normalized_model,
        "estimated_cost_usd": round(max(0.0, float(estimated_cost_usd)), 8),
        "cloud_call_made": False,
        "policy": policy,
    }

    if policy is None:
        return {**base, "allowed": False, "effect": "deny", "reason": "No policy exists for this domain."}

    if normalized_provider not in {"local", "openai"}:
        return {**base, "allowed": False, "effect": "deny", "reason": "The requested provider is not supported."}

    if normalized_provider == "openai" and not policy["cloud_allowed"]:
        return {**base, "allowed": False, "effect": "deny", "reason": "Cloud models are disabled for this domain."}

    model_key = "local" if normalized_provider == "local" else normalized_model
    if model_key not in policy["allowed_models"]:
        return {**base, "allowed": False, "effect": "deny", "reason": "The requested model is not allowed for this domain."}

    if base["estimated_cost_usd"] > policy["max_request_usd"]:
        return {**base, "allowed": False, "effect": "deny", "reason": "The estimate exceeds this domain's per-request limit."}

    budget_decision = budget_service.evaluate_estimate(base["estimated_cost_usd"])
    base["budget"] = budget_decision
    if not budget_decision["allowed"]:
        return {**base, "allowed": False, "effect": "deny", "reason": budget_decision["reason"]}

    if normalized_provider == "openai" and policy["approval_required"] and not approved:
        return {
            **base,
            "allowed": False,
            "effect": "approval_required",
            "reason": "Human approval is required before this domain may use a cloud model.",
        }

    return {
        **base,
        "allowed": True,
        "effect": "allow",
        "reason": "The simulated request satisfies the domain and budget policies.",
    }


def evaluate(*, user_id: str, domain: str, capability: str) -> PolicyDecision:
    state = get_control_state()
    normalized_domain = domain.strip().lower()
    normalized_capability = capability.strip().lower()

    if normalized_capability in READ_CAPABILITIES:
        return PolicyDecision(
            True,
            normalized_capability,
            normalized_domain,
            state["mode"],
            "allow",
            "Conversation and read-only access remain available.",
        )

    if state["mode"] == "emergency_stop" and normalized_capability in AUTONOMOUS_CAPABILITIES:
        return PolicyDecision(
            False,
            normalized_capability,
            normalized_domain,
            state["mode"],
            "deny",
            "The emergency stop blocks all autonomous and agent actions.",
        )

    if state["mode"] == "paused" and normalized_capability in AUTONOMOUS_CAPABILITIES:
        return PolicyDecision(
            False,
            normalized_capability,
            normalized_domain,
            state["mode"],
            "deny",
            "Global autonomy is paused.",
        )

    with connection() as conn:
        permission = conn.execute(
            """
            SELECT * FROM permissions
            WHERE user_id = ? AND domain = ? AND capability = ?
            """,
            (user_id, normalized_domain, normalized_capability),
        ).fetchone()

    if permission and permission["effect"] == "allow":
        return PolicyDecision(
            True,
            normalized_capability,
            normalized_domain,
            state["mode"],
            "allow",
            "An explicit permission allows this capability.",
            permission["id"],
        )
    if permission:
        return PolicyDecision(
            False,
            normalized_capability,
            normalized_domain,
            state["mode"],
            permission["effect"],
            "The configured permission does not allow automatic execution.",
            permission["id"],
        )

    default_allowed = normalized_capability == "manual_write"
    return PolicyDecision(
        default_allowed,
        normalized_capability,
        normalized_domain,
        state["mode"],
        "allow" if default_allowed else "deny",
        "Owner-initiated manual writes are allowed."
        if default_allowed
        else "No explicit permission allows this capability.",
    )


def require(*, user_id: str, domain: str, capability: str) -> PolicyDecision:
    decision = evaluate(user_id=user_id, domain=domain, capability=capability)
    if not decision.allowed:
        raise PolicyDeniedError(decision)
    return decision
