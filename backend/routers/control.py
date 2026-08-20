from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from routers.auth import current_session, require_csrf
from services import audit_service, policy_service


router = APIRouter(prefix="/api/vera", tags=["vera-control"])


class ControlChangeRequest(BaseModel):
    reason: str = Field(default="", max_length=500)
    expected_version: Optional[int] = Field(default=None, ge=1)


class PermissionRequest(BaseModel):
    domain: str = Field(min_length=1, max_length=100)
    capability: str = Field(min_length=1, max_length=100)
    effect: Literal["allow", "deny", "approval_required"]


class DomainPolicyEvaluationRequest(BaseModel):
    domain: str = Field(min_length=1, max_length=100)
    provider: Literal["local", "openai"]
    model: str = Field(min_length=1, max_length=100)
    estimated_cost_usd: float = Field(default=0, ge=0, le=1000)
    approved: bool = False


def _change_mode(mode: str, request: ControlChangeRequest, session: dict) -> dict:
    before = policy_service.get_control_state()
    try:
        state = policy_service.set_control_mode(
            mode=mode,
            actor_user_id=session["user_id"],
            reason=request.reason,
            expected_version=request.expected_version,
        )
    except policy_service.ControlVersionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    audit_service.append_event(
        actor_user_id=session["user_id"],
        action=f"control.{mode}",
        resource_type="control_state",
        resource_id="global",
        outcome="succeeded",
        details={
            "previous_mode": before["mode"],
            "mode": state["mode"],
            "version": state["version"],
            "reason": state["reason"],
        },
    )
    return {"control": state}


@router.get("/control")
def get_control(session: dict = Depends(current_session)):
    return {"control": policy_service.get_control_state()}


@router.post("/control/pause")
def pause_control(request: ControlChangeRequest, session: dict = Depends(require_csrf)):
    return _change_mode("paused", request, session)


@router.post("/control/emergency-stop")
def emergency_stop(request: ControlChangeRequest, session: dict = Depends(require_csrf)):
    return _change_mode("emergency_stop", request, session)


@router.post("/control/resume")
def resume_control(request: ControlChangeRequest, session: dict = Depends(require_csrf)):
    return _change_mode("active", request, session)


@router.get("/permissions")
def get_permissions(session: dict = Depends(current_session)):
    return {"permissions": policy_service.list_permissions(session["user_id"])}


@router.put("/permissions")
def put_permission(request: PermissionRequest, session: dict = Depends(require_csrf)):
    permission = policy_service.set_permission(
        user_id=session["user_id"],
        domain=request.domain,
        capability=request.capability,
        effect=request.effect,
    )
    audit_service.append_event(
        actor_user_id=session["user_id"],
        action="permission.updated",
        resource_type="permission",
        resource_id=permission["id"],
        outcome="succeeded",
        details={
            "domain": permission["domain"],
            "capability": permission["capability"],
            "effect": permission["effect"],
        },
    )
    return {"permission": permission}


@router.get("/policies/domains")
def get_domain_policies(session: dict = Depends(current_session)):
    return {"policies": policy_service.list_domain_policies(), "mode": "simulation"}


@router.post("/policies/evaluate")
def evaluate_domain_policy(
    request: DomainPolicyEvaluationRequest,
    session: dict = Depends(current_session),
):
    return policy_service.evaluate_domain_request(
        domain=request.domain,
        provider=request.provider,
        model=request.model,
        estimated_cost_usd=request.estimated_cost_usd,
        approved=request.approved,
    )


@router.get("/audit")
def get_audit(limit: int = 100, session: dict = Depends(current_session)):
    return {"events": audit_service.list_events(limit)}
