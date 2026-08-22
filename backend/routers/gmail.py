from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from routers.auth import current_session, require_csrf
from services import audit_service, gmail_service


router = APIRouter(prefix="/api/gmail", tags=["gmail"])


@router.get("/status")
def status(session: dict = Depends(current_session)):
    return gmail_service.get_status(session["user_id"])


@router.post("/oauth/start")
def oauth_start(session: dict = Depends(require_csrf)):
    try:
        return {"authorization_url": gmail_service.authorization_url(session["user_id"])}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/oauth/callback")
def oauth_callback(state: str = Query(min_length=16), code: str = Query(min_length=1)):
    try:
        result = gmail_service.complete_authorization(state, code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Gmail authorization could not be completed.") from exc
    user_id = result.pop("_user_id")
    audit_service.append_event(
        actor_user_id=user_id,
        action="gmail.connected",
        resource_type="gmail_connection",
        resource_id=result["email_address"],
        outcome="succeeded",
        details={"access": "read_only", "scopes": result["scopes"]},
    )
    return RedirectResponse(url="/?gmail=connected", status_code=303)


@router.post("/disconnect")
def disconnect(session: dict = Depends(require_csrf)):
    result = gmail_service.disconnect(session["user_id"])
    audit_service.append_event(
        actor_user_id=session["user_id"],
        action="gmail.disconnected",
        resource_type="gmail_connection",
        resource_id=session["user_id"],
        outcome="succeeded",
        details=result,
    )
    return result
