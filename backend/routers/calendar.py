from fastapi import APIRouter, Depends, HTTPException, Query

from routers.auth import current_session, require_csrf
from services import agent_permission_service, audit_service, calendar_service


router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("/status")
def status(session: dict = Depends(current_session)):
    return calendar_service.get_status(session["user_id"])


@router.post("/oauth/start")
def oauth_start(session: dict = Depends(require_csrf)):
    return {"authorization_url": calendar_service.authorization_url(session["user_id"])}


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
