from fastapi import APIRouter, Depends

from routers.auth import current_session
from services import audit_service, home_assistant_service


router = APIRouter(prefix="/api/home-assistant", tags=["home-assistant"])


@router.get("/status")
def status(session: dict = Depends(current_session)):
    return home_assistant_service.get_status(check_connection=True)


@router.get("/overview")
def overview(session: dict = Depends(current_session)):
    result = home_assistant_service.get_overview()
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
