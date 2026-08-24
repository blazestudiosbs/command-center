import sqlite3

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from routers.auth import current_session, require_csrf
from services import audit_service, multi_server_service

router = APIRouter(prefix="/api/servers", tags=["servers"])


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    hostname: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class EnabledRequest(BaseModel):
    enabled: bool


class HeartbeatStatus(BaseModel):
    uptime_seconds: int = Field(ge=0)
    load_1m: float = Field(ge=0)
    memory_used_percent: float = Field(ge=0, le=100)
    disk_used_percent: float = Field(ge=0, le=100)
    services_running: int = Field(ge=0)
    services_total: int = Field(ge=0)


class HeartbeatRequest(BaseModel):
    agent_version: str = Field(min_length=1, max_length=30)
    status: HeartbeatStatus


@router.get("")
def servers(session: dict = Depends(current_session)):
    return {"servers": multi_server_service.list_servers(session["user_id"]), "remote_execution": False}


@router.post("")
def register(request: RegisterRequest, session: dict = Depends(require_csrf)):
    try:
        server = multi_server_service.register(session["user_id"], **request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="That hostname is already registered.") from exc
    audit_service.append_event(actor_user_id=session["user_id"], action="server.registered", resource_type="managed_server", resource_id=server["id"], outcome="succeeded", details={"hostname": server["hostname"]})
    return {"server": server}


@router.put("/{server_id}/enabled")
def enabled(server_id: str, request: EnabledRequest, session: dict = Depends(require_csrf)):
    try:
        server = multi_server_service.set_enabled(session["user_id"], server_id, request.enabled)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"server": server}


@router.post("/{server_id}/rotate-token")
def rotate(server_id: str, session: dict = Depends(require_csrf)):
    try:
        server = multi_server_service.rotate_token(session["user_id"], server_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit_service.append_event(actor_user_id=session["user_id"], action="server.token_rotated", resource_type="managed_server", resource_id=server_id, outcome="succeeded")
    return {"server": server}


@router.post("/heartbeat")
def heartbeat(request: HeartbeatRequest, authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Server token required.")
    try:
        server = multi_server_service.record_heartbeat(authorization[7:].strip(), agent_version=request.agent_version, status=request.status.model_dump())
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"accepted": True, "server_id": server["id"]}
