from fastapi import APIRouter, Depends
from pydantic import BaseModel

from routers.auth import current_session, require_csrf
from services import audit_service, infrastructure_service


router = APIRouter(prefix="/api/infrastructure", tags=["infrastructure"])


class SettingsRequest(BaseModel):
    security_updates_enabled: bool
    health_checks_enabled: bool


@router.get("/status")
def status(_session: dict = Depends(current_session)):
    return infrastructure_service.get_status()


@router.put("/settings")
def settings(request: SettingsRequest, session: dict = Depends(require_csrf)):
    result = infrastructure_service.set_settings(**request.model_dump())
    audit_service.append_event(actor_user_id=session["user_id"], action="infrastructure.settings_updated", resource_type="infrastructure_agent", resource_id="global", outcome="succeeded", details=result)
    return result
