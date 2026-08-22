from fastapi import APIRouter, Depends

from routers.auth import current_session
from services import service_monitoring_service


router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


@router.get("/status")
def status(_session: dict = Depends(current_session)):
    return service_monitoring_service.get_status()
