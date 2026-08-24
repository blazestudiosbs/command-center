import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import current_session, require_csrf
from services import agent_permission_service, audit_service, daily_briefing_service

router = APIRouter(prefix="/api/daily-briefing", tags=["daily-briefing"])


class SettingsRequest(BaseModel):
    enabled: bool
    delivery_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    include_calendar: bool
    include_gmail: bool
    include_infrastructure: bool
    include_backups: bool
    include_approvals: bool


@router.get("/status")
def status(session: dict = Depends(current_session)):
    return {"settings": daily_briefing_service.get_settings(session["user_id"]), "discord_configured": bool(os.getenv("DISCORD_WEBHOOK", "").strip())}


@router.put("/settings")
def settings(request: SettingsRequest, session: dict = Depends(require_csrf)):
    result = daily_briefing_service.set_settings(session["user_id"], **request.model_dump())
    audit_service.append_event(actor_user_id=session["user_id"], action="briefing.settings_updated", resource_type="daily_briefing", resource_id="owner", outcome="succeeded", details=result)
    return result


@router.post("/preview")
def preview(session: dict = Depends(require_csrf)):
    try:
        briefing = daily_briefing_service.generate(session["user_id"])
    except agent_permission_service.AgentPermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail="Enable Daily Briefing Agent → Generate local briefings first.") from exc
    return {"briefing": briefing, "message": daily_briefing_service.format_message(briefing)}


@router.post("/send")
def send(session: dict = Depends(require_csrf)):
    try:
        agent_permission_service.require(session["user_id"], "daily_briefing", "scheduled_delivery")
        result = daily_briefing_service.run(session["user_id"], mode="manual")
    except agent_permission_service.AgentPermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail="Enable Daily Briefing Agent delivery permissions first.") from exc
    if result["status"] != "sent":
        raise HTTPException(status_code=502, detail="The briefing was generated but Discord delivery failed safely.")
    return result
