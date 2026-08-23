from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import current_session, require_csrf
from services import agent_permission_service, audit_service, release_service

router = APIRouter(prefix="/api/releases", tags=["releases"])


class PrepareRequest(BaseModel):
    commit_message: str = Field(min_length=1, max_length=120)
    deploy: bool = True


class ExecuteRequest(BaseModel):
    release_id: str = Field(min_length=1, max_length=100)


@router.get("/status")
def status(session: dict = Depends(current_session)):
    return {**release_service.connection_status(), "releases": release_service.list_releases(session["user_id"])}


@router.post("/prepare")
def prepare(request: PrepareRequest, session: dict = Depends(require_csrf)):
    try:
        agent_permission_service.require(session["user_id"], "development_worker", "prepare_releases")
        result = release_service.prepare(session["user_id"], commit_message=request.commit_message, deploy_requested=request.deploy)
    except agent_permission_service.AgentPermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail="Enable Development Worker → Prepare releases first.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_service.append_event(actor_user_id=session["user_id"], action="release.prepared", resource_type="release", resource_id=result["id"], outcome="pending_confirmation", details={"branch": result["branch"], "file_count": len(result["files"]), "deploy": result["deploy_requested"]})
    return {"release": result}


@router.post("/execute")
def execute(request: ExecuteRequest, session: dict = Depends(require_csrf)):
    try:
        agent_permission_service.require(session["user_id"], "development_worker", "execute_approved_releases")
        result = release_service.execute(session["user_id"], request.release_id)
    except agent_permission_service.AgentPermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail="Enable Development Worker → Execute approved releases first.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    audit_service.append_event(actor_user_id=session["user_id"], action="release.executed", resource_type="release", resource_id=result["id"], outcome="succeeded", details={"commit_hash": result["commit_hash"], "pushed": True, "deployment_started": result["deployment_started"]})
    return result
