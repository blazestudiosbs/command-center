from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import current_session, require_csrf
from services import agent_permission_service, audit_service


router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentPermissionRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=100)
    capability: str = Field(min_length=1, max_length=100)
    enabled: bool


@router.get("")
def agents(session: dict = Depends(current_session)):
    return {"agents": agent_permission_service.list_agents(session["user_id"])}


@router.put("/permissions")
def update_permission(request: AgentPermissionRequest, session: dict = Depends(require_csrf)):
    try:
        agent = agent_permission_service.set_permission(
            user_id=session["user_id"],
            agent_id=request.agent_id,
            capability=request.capability,
            enabled=request.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.append_event(
        actor_user_id=session["user_id"],
        action="agent.permission_updated",
        resource_type="agent_permission",
        resource_id=f"{request.agent_id}:{request.capability}",
        outcome="succeeded",
        details={"agent_id": request.agent_id, "capability": request.capability, "enabled": request.enabled},
    )
    return {"agent": agent}
