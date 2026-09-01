import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from routers.auth import current_session, require_csrf
from services import agent_permission_service, audit_service, home_assistant_service


router = APIRouter(prefix="/api/home-assistant", tags=["home-assistant"])


class LightPermissionRequest(BaseModel):
    entity_id: str = Field(min_length=7, max_length=255, pattern=r"^light\.[a-z0-9_]+$")
    enabled: bool


class LightActionRequest(BaseModel):
    entity_id: str = Field(min_length=7, max_length=255, pattern=r"^light\.[a-z0-9_]+$")
    action: str = Field(pattern=r"^(turn_on|turn_off)$")


class LightConfirmationRequest(BaseModel):
    action_id: str = Field(min_length=1, max_length=100)


class DirectLightActionRequest(BaseModel):
    entity_id: str = Field(min_length=7, max_length=255, pattern=r"^light\.[a-z0-9_]+$")
    action: str = Field(pattern=r"^(turn_on|turn_off)$")
    brightness: int | None = Field(default=None, ge=1, le=255)
    color_temp_kelvin: int | None = Field(default=None, ge=1500, le=10000)
    rgb_color: tuple[int, int, int] | None = None
    effect: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def settings_require_turn_on(self):
        if self.action == "turn_off" and any(value is not None for value in (self.brightness, self.color_temp_kelvin, self.rgb_color, self.effect)):
            raise ValueError("Light settings require turn_on.")
        return self


@router.get("/status")
def status(session: dict = Depends(current_session)):
    return home_assistant_service.get_status(check_connection=True)


@router.get("/overview")
def overview(session: dict = Depends(current_session)):
    try:
        agent_permission_service.require(session["user_id"], "home_assistant", "read_devices")
    except agent_permission_service.AgentPermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail="Enable Home Assistant Agent → Read device states first.") from exc
    result = home_assistant_service.get_overview()
    permissions = home_assistant_service.light_permissions(session["user_id"])
    result["entities"] = [{**entity, "control_enabled": permissions.get(entity["entity_id"], False) if entity["domain"] == "light" else False} for entity in result["entities"]]
    audit_service.append_event(
        actor_user_id=session["user_id"],
        action="home_assistant.read",
        resource_type="home_assistant",
        resource_id="overview",
        outcome="succeeded" if result["status"]["connection_status"] == "connected" else "failed",
        details={
            "connection_status": result["status"]["connection_status"],
            "entity_count": len(result["entities"]),
            "read_only": True,
        },
    )
    return result


@router.put("/lights/permissions")
def light_permission(request: LightPermissionRequest, session: dict = Depends(require_csrf)):
    result = home_assistant_service.set_light_permission(session["user_id"], request.entity_id, request.enabled)
    audit_service.append_event(actor_user_id=session["user_id"], action="home.light_permission_updated", resource_type="home_assistant_entity", resource_id=request.entity_id, outcome="succeeded", details={"enabled": request.enabled})
    return {"permission": result}


@router.get("/lights/actions/pending")
def pending_light_actions(session: dict = Depends(current_session)):
    return {"actions": home_assistant_service.pending_light_actions(session["user_id"])}


@router.post("/lights/actions/prepare")
def prepare_light_action(request: LightActionRequest, session: dict = Depends(require_csrf)):
    try:
        agent_permission_service.require(session["user_id"], "home_assistant", "control_lights")
        result = home_assistant_service.prepare_light_action(session["user_id"], **request.model_dump())
    except agent_permission_service.AgentPermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail="Enable Home Assistant Agent → Prepare and confirm approved light controls first.") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RuntimeError, requests.RequestException) as exc:
        raise HTTPException(status_code=502, detail="Home Assistant could not validate this light safely.") from exc
    audit_service.append_event(actor_user_id=session["user_id"], action=f"home.light_{request.action}_prepared", resource_type="home_light_action", resource_id=result["id"], outcome="allowed", details={"entity_id": request.entity_id, "expires_utc": result["expires_utc"]})
    return {"action": result}


@router.post("/lights/actions/confirm")
def confirm_light_action(request: LightConfirmationRequest, session: dict = Depends(require_csrf)):
    try:
        agent_permission_service.require(session["user_id"], "home_assistant", "control_lights")
        result = home_assistant_service.confirm_light_action(session["user_id"], request.action_id)
    except agent_permission_service.AgentPermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail="The Home Assistant light-control permission is off.") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (RuntimeError, requests.RequestException) as exc:
        audit_service.append_event(actor_user_id=session["user_id"], action="home.light_confirmation_failed", resource_type="home_light_action", resource_id=request.action_id, outcome="failed", details={"reason": str(exc)[:300]})
        raise HTTPException(status_code=502, detail="Home Assistant did not verify the confirmed light action.") from exc
    audit_service.append_event(actor_user_id=session["user_id"], action=f"home.light_{result['action']}_confirmed", resource_type="home_assistant_entity", resource_id=result["entity_id"], outcome="succeeded", details={"action_id": request.action_id, "before_state": result["before_state"], "observed_state": result["observed_state"], "verified": result["verified"]})
    return result


@router.post("/lights/actions/execute")
def execute_light_action(request: DirectLightActionRequest, session: dict = Depends(require_csrf)):
    try:
        agent_permission_service.require(session["user_id"], "home_assistant", "control_lights")
        result = home_assistant_service.execute_light_action(session["user_id"], **request.model_dump())
    except agent_permission_service.AgentPermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail="The Home Assistant light-control permission is off.") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RuntimeError, requests.RequestException) as exc:
        audit_service.append_event(actor_user_id=session["user_id"], action="home.light_direct_failed", resource_type="home_assistant_entity", resource_id=request.entity_id, outcome="failed", details={"reason": str(exc)[:300]})
        raise HTTPException(status_code=502, detail="Home Assistant did not verify the light action.") from exc
    audit_service.append_event(actor_user_id=session["user_id"], action=f"home.light_{request.action}_direct", resource_type="home_assistant_entity", resource_id=request.entity_id, outcome="succeeded", details={"requested": request.model_dump(exclude_none=True), "observed": result["observed"], "verified": True})
    return result
