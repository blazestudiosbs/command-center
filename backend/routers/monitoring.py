from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import current_session, require_csrf
from services import audit_service, service_monitoring_service


router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


class ServicePreference(BaseModel):
    container_name: str = Field(min_length=1, max_length=200)
    outage_alerts_enabled: bool
    recovery_alerts_enabled: bool


class NotificationPreferencesRequest(BaseModel):
    alerts_enabled: bool
    cooldown_seconds: int = Field(ge=0, le=86400)
    services: list[ServicePreference]


@router.get("/status")
def status(_session: dict = Depends(current_session)):
    return service_monitoring_service.get_status()


@router.get("/notifications")
def notifications(_session: dict = Depends(current_session)):
    return service_monitoring_service.get_notification_preferences()


@router.put("/notifications")
def update_notifications(
    request: NotificationPreferencesRequest,
    session: dict = Depends(require_csrf),
):
    try:
        preferences = service_monitoring_service.set_notification_preferences(
            alerts_enabled=request.alerts_enabled,
            cooldown=request.cooldown_seconds,
            services=[item.model_dump() for item in request.services],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.append_event(
        actor_user_id=session["user_id"],
        action="service_monitor.notifications_updated",
        resource_type="monitoring_notification_preferences",
        resource_id="global",
        outcome="succeeded",
        details={
            "alerts_enabled": preferences["alerts_enabled"],
            "cooldown_seconds": preferences["cooldown_seconds"],
            "service_count": len(preferences["services"]),
        },
    )
    return preferences
