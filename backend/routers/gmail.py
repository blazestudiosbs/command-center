from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from routers.auth import current_session, require_csrf
from services import agent_permission_service, audit_service, gmail_service


router = APIRouter(prefix="/api/gmail", tags=["gmail"])


class LearnSenderRequest(BaseModel):
    sender: str = Field(min_length=3, max_length=500)
    category: str = Field(min_length=1, max_length=100)


class OrganizerSettingsRequest(BaseModel):
    enabled: bool


@router.get("/status")
def status(session: dict = Depends(current_session)):
    return gmail_service.get_status(session["user_id"])


@router.post("/oauth/start")
def oauth_start(session: dict = Depends(require_csrf)):
    try:
        return {"authorization_url": gmail_service.authorization_url(session["user_id"])}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/oauth/callback")
def oauth_callback(state: str = Query(min_length=16), code: str = Query(min_length=1)):
    try:
        result = gmail_service.complete_authorization(state, code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Gmail authorization could not be completed.") from exc
    user_id = result.pop("_user_id")
    audit_service.append_event(
        actor_user_id=user_id,
        action="gmail.connected",
        resource_type="gmail_connection",
        resource_id=result["email_address"],
        outcome="succeeded",
        details={"access": "read_only", "scopes": result["scopes"]},
    )
    return RedirectResponse(url="/?gmail=connected", status_code=303)


@router.post("/disconnect")
def disconnect(session: dict = Depends(require_csrf)):
    result = gmail_service.disconnect(session["user_id"])
    audit_service.append_event(
        actor_user_id=session["user_id"],
        action="gmail.disconnected",
        resource_type="gmail_connection",
        resource_id=session["user_id"],
        outcome="succeeded",
        details=result,
    )
    return result


@router.post("/organizer/preview")
def organizer_preview(session: dict = Depends(require_csrf)):
    try:
        agent_permission_service.require(session["user_id"], "gmail", "read_inbox")
    except agent_permission_service.AgentPermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail="Enable Gmail Agent → Read inbox in Agent Permissions first.") from exc
    try:
        result = gmail_service.organizer_preview(session["user_id"])
    except Exception as exc:
        audit_service.append_event(
            actor_user_id=session["user_id"], action="gmail.organizer_preview",
            resource_type="gmail_connection", resource_id=session["user_id"], outcome="failed",
            details={"error_type": type(exc).__name__, "cloud_processing": False},
        )
        raise HTTPException(status_code=502, detail="Gmail organizer preview could not be loaded.") from exc
    audit_service.append_event(
        actor_user_id=session["user_id"], action="gmail.organizer_preview",
        resource_type="gmail_connection", resource_id=session["user_id"], outcome="succeeded",
        details={"message_count": result["message_count"], "simulation": True, "cloud_processing": False},
    )
    return result


@router.get("/learning/status")
def learning_status(session: dict = Depends(current_session)):
    return gmail_service.get_learning_status(session["user_id"])


@router.post("/learning/sender-rule")
def learn_sender(request: LearnSenderRequest, session: dict = Depends(require_csrf)):
    try:
        agent_permission_service.require(session["user_id"], "gmail", "read_inbox")
        rule = gmail_service.learn_sender_rule(session["user_id"], request.sender, request.category)
    except agent_permission_service.AgentPermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail="Enable Gmail Agent → Read inbox first.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.append_event(
        actor_user_id=session["user_id"], action="gmail.classification_learned",
        resource_type="gmail_classification_rule", resource_id=rule["id"], outcome="succeeded",
        details={"match_type": "sender", "category": rule["category"], "source": "user"},
    )
    return {"rule": rule, "learning": gmail_service.get_learning_status(session["user_id"])}


@router.get("/organizer/settings")
def organizer_settings(session: dict = Depends(current_session)):
    return gmail_service.get_organizer_settings(session["user_id"])


@router.put("/organizer/settings")
def update_organizer_settings(request: OrganizerSettingsRequest, session: dict = Depends(require_csrf)):
    if request.enabled:
        try:
            agent_permission_service.require(session["user_id"], "gmail", "organize_and_file")
        except agent_permission_service.AgentPermissionDeniedError as exc:
            raise HTTPException(status_code=403, detail="Enable Gmail Agent → Organize and remove from Inbox first.") from exc
    try:
        settings = gmail_service.set_organizer_enabled(session["user_id"], request.enabled)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_service.append_event(
        actor_user_id=session["user_id"], action="gmail.organizer_enabled" if request.enabled else "gmail.organizer_disabled",
        resource_type="gmail_organizer", resource_id=session["user_id"], outcome="succeeded",
        details={"enabled": request.enabled, "remove_inbox": True},
    )
    return settings


@router.post("/organizer/run")
def run_organizer(session: dict = Depends(require_csrf)):
    try:
        agent_permission_service.require(session["user_id"], "gmail", "organize_and_file")
        result = gmail_service.run_organizer(session["user_id"], include_existing=True)
    except agent_permission_service.AgentPermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Gmail organizer run failed safely.") from exc
    audit_service.append_event(
        actor_user_id=session["user_id"], action="gmail.organizer_run", resource_type="gmail_organizer",
        resource_id=session["user_id"], outcome="succeeded" if not result["failed"] else "failed", details=result,
    )
    return result
