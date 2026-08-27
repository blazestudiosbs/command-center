from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import current_session, require_csrf
from services import audit_service, household_service


router = APIRouter(prefix="/api/household", tags=["household"])


class VoiceIdentityLinkRequest(BaseModel):
    member_id: str = Field(min_length=1, max_length=100)
    provider: str = Field(default="amazon_alexa", pattern=r"^[a-z0-9_]{1,50}$")
    subject_id: str = Field(min_length=1, max_length=500)


@router.get("/members")
def members(_session: dict = Depends(current_session)):
    return {"members": household_service.list_members()}


@router.post("/voice-identities")
def link_voice_identity(request: VoiceIdentityLinkRequest, session: dict = Depends(require_csrf)):
    try:
        result = household_service.link_voice_identity(**request.model_dump())
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.append_event(
        actor_user_id=session["user_id"],
        action="household.voice_identity_linked",
        resource_type="household_member",
        resource_id=request.member_id,
        outcome="succeeded",
        details={"provider": request.provider},
    )
    return {"identity": result}
