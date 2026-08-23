from fastapi import APIRouter, Depends

from routers.auth import current_session
from services import project_awareness_service


router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("/awareness")
def awareness(_session: dict = Depends(current_session)):
    return project_awareness_service.get_overview()
