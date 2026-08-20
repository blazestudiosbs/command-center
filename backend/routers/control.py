from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from routers.auth import current_session, require_csrf
from services import audit_service, policy_service, router_service


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


class RoutingSimulationRequest(BaseModel):
    domain: str = Field(default="general", min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=1_000_000)
    max_output_tokens: int = Field(default=400, ge=0, le=32768)
    local_available: bool = True
    local_confidence: float = Field(default=1.0, ge=0, le=1)
    approved: bool = False


class CloudRoutingChangeRequest(BaseModel):
    reason: str = Field(default="", max_length=500)
    expected_version: Optional[int] = Field(default=None, ge=1)


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
    cloud_disabled = False
    cloud_state = router_service.get_cloud_routing_state()
    if mode != "active" and cloud_state["enabled"]:
        router_service.set_cloud_routing(
            enabled=False,
            actor_user_id=session["user_id"],
            reason=f"Cloud routing disabled by global {mode} control",
            expected_version=cloud_state["version"],
        )
        cloud_disabled = True
        audit_service.append_event(
            actor_user_id=session["user_id"],
            action="cloud_routing.disabled",
            resource_type="cloud_routing_state",
            resource_id="global",
            outcome="succeeded",
            details={"reason": f"Global control changed to {mode}."},
        )
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
            "cloud_routing_disabled": cloud_disabled,
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


@router.get("/router/status")
def get_router_status(session: dict = Depends(current_session)):
    return router_service.get_status()


@router.get("/router/cloud")
def get_cloud_routing(session: dict = Depends(current_session)):
    return {"cloud_routing": router_service.get_cloud_routing_state()}


def _change_cloud_routing(enabled: bool, request: CloudRoutingChangeRequest, session: dict):
    before = router_service.get_cloud_routing_state()
    try:
        state = router_service.set_cloud_routing(
            enabled=enabled,
            actor_user_id=session["user_id"],
            reason=request.reason,
            expected_version=request.expected_version,
        )
    except router_service.CloudRoutingVersionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except router_service.CloudRoutingUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=str(exc)) from exc
    audit_service.append_event(
        actor_user_id=session["user_id"],
        action="cloud_routing.enabled" if enabled else "cloud_routing.disabled",
        resource_type="cloud_routing_state",
        resource_id="global",
        outcome="succeeded",
        details={
            "previous_enabled": before["enabled"],
            "enabled": state["enabled"],
            "version": state["version"],
            "reason": state["reason"],
        },
    )
    return {"cloud_routing": state}


@router.post("/router/cloud/enable")
def enable_cloud_routing(
    request: CloudRoutingChangeRequest,
    session: dict = Depends(require_csrf),
):
    return _change_cloud_routing(True, request, session)


@router.post("/router/cloud/disable")
def disable_cloud_routing(
    request: CloudRoutingChangeRequest,
    session: dict = Depends(require_csrf),
):
    return _change_cloud_routing(False, request, session)


@router.post("/router/simulate")
def simulate_route(
    request: RoutingSimulationRequest,
    session: dict = Depends(current_session),
):
    return router_service.simulate(
        domain=request.domain,
        prompt=request.prompt,
        max_output_tokens=request.max_output_tokens,
        local_available=request.local_available,
        local_confidence=request.local_confidence,
        approved=request.approved,
    )


@router.get("/router/decisions")
def get_routing_decisions(limit: int = 100, session: dict = Depends(current_session)):
    return {"decisions": router_service.list_decisions(limit)}


@router.get("/audit")
def get_audit(limit: int = 100, session: dict = Depends(current_session)):
    return {"events": audit_service.list_events(limit)}
