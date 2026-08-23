from fastapi import APIRouter, Depends
from pydantic import BaseModel

from routers.auth import current_session, require_csrf
from services import audit_service, backup_service


router = APIRouter(prefix="/api/backups", tags=["backups"])


class BackupSettingsRequest(BaseModel):
    enabled: bool


@router.get("/status")
def status(_session: dict = Depends(current_session)):
    return backup_service.get_status()


@router.put("/settings")
def settings(request: BackupSettingsRequest, session: dict = Depends(require_csrf)):
    result = backup_service.set_enabled(request.enabled)
    audit_service.append_event(actor_user_id=session["user_id"], action="backup.enabled" if request.enabled else "backup.disabled", resource_type="backup_agent", resource_id="global", outcome="succeeded", details={"enabled": request.enabled})
    return result
