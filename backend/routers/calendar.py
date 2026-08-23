import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from routers.auth import current_session, require_csrf
from services import agent_permission_service, audit_service, calendar_service


router = APIRouter(prefix="/api/calendar", tags=["calendar"])


class CalendarChangeRequest(BaseModel):
    action: str = Field(pattern="^(create|edit|delete)$")
    event_id: str | None = Field(default=None, max_length=1024)
    title: str | None = Field(default=None, max_length=300)
    start: str | None = Field(default=None, max_length=50)
    end: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=500)
    all_day: bool = False


class CalendarConfirmationRequest(BaseModel):
    change_id: str = Field(min_length=1, max_length=100)


@router.get("/status")
def status(session: dict = Depends(current_session)):
    return calendar_service.get_status(session["user_id"])


@router.post("/oauth/start")
def oauth_start(write: bool = Query(default=False), session: dict = Depends(require_csrf)):
    return {"authorization_url": calendar_service.authorization_url(session["user_id"], write=write)}


@router.get("/events")
def events(days: int = Query(default=7, ge=1, le=31), session: dict = Depends(current_session)):
    try:
        agent_permission_service.require(session["user_id"], "calendar", "read_events")
        result = calendar_service.upcoming(session["user_id"], days=days)
    except agent_permission_service.AgentPermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail="Enable Calendar Agent → Read event titles and times first.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_service.append_event(actor_user_id=session["user_id"], action="calendar.read", resource_type="calendar_connection", resource_id="primary", outcome="succeeded", details={"event_count": len(result), "read_only": True})
    return {"events": result, "days": days, "time_zone": "America/Detroit"}


@router.get("/changes/pending")
def pending_changes(session: dict = Depends(current_session)):
    return {"changes": calendar_service.pending_changes(session["user_id"])}


@router.post("/changes/prepare")
def prepare_change(request: CalendarChangeRequest, session: dict = Depends(require_csrf)):
    try:
        agent_permission_service.require(session["user_id"], "calendar", request.action)
        result = calendar_service.prepare_change(session["user_id"], **request.model_dump())
    except agent_permission_service.AgentPermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=f"Enable Calendar Agent → {request.action.title()} confirmed events first.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="Google Calendar could not prepare this change.") from exc
    audit_service.append_event(actor_user_id=session["user_id"], action=f"calendar.{request.action}_prepared", resource_type="calendar_change", resource_id=result["id"], outcome="pending_confirmation", details={"event_id": request.event_id, "expires_utc": result["expires_utc"]})
    return {"change": result, "cloud_call_made": False}


@router.post("/changes/confirm")
def confirm_change(request: CalendarConfirmationRequest, session: dict = Depends(require_csrf)):
    try:
        action = calendar_service.pending_change_action(session["user_id"], request.change_id)
        agent_permission_service.require(session["user_id"], "calendar", action)
        result = calendar_service.confirm_change(session["user_id"], request.change_id)
    except agent_permission_service.AgentPermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail="The required Calendar Agent permission is disabled.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="Google Calendar did not complete the confirmed change.") from exc
    audit_service.append_event(actor_user_id=session["user_id"], action=f"calendar.{result['action']}_confirmed", resource_type="calendar_event", resource_id=result["event"].get("id") or "primary", outcome="succeeded", details={"change_id": request.change_id})
    return result
