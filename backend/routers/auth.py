import hmac
import os

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field

from services import auth_service


router = APIRouter(prefix="/api/auth", tags=["authentication"])
COOKIE_NAME = "vera_session"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=512)


def _cookie_secure() -> bool:
    return os.getenv("VERA_COOKIE_SECURE", "true").lower() not in {"0", "false", "no"}


def current_session(
    session_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> dict:
    session = auth_service.get_session(session_token or "")
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return session


def require_csrf(
    session: dict = Depends(current_session),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    if not csrf_token or not hmac.compare_digest(csrf_token, session["csrf_token"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")
    return session


def _user_payload(session: dict) -> dict:
    return {
        "id": session["user_id"],
        "username": session["username"],
        "role": session["role"],
    }


@router.post("/login")
def login(request: LoginRequest, response: Response):
    if not auth_service.configured_password_hash():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vera authentication is not configured.",
        )
    user = auth_service.authenticate(request.username.strip(), request.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    session = auth_service.create_session(user["id"])
    response.set_cookie(
        key=COOKIE_NAME,
        value=session["token"],
        max_age=auth_service.SESSION_HOURS * 60 * 60,
        httponly=True,
        secure=_cookie_secure(),
        samesite="strict",
        path="/",
    )
    return {"user": user, "csrf_token": session["csrf_token"], "expires_utc": session["expires_utc"]}


@router.get("/me")
def me(session: dict = Depends(current_session)):
    return {"user": _user_payload(session), "csrf_token": session["csrf_token"]}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session: dict = Depends(require_csrf),
    session_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
):
    auth_service.delete_session(session_token or "")
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        secure=_cookie_secure(),
        httponly=True,
        samesite="strict",
    )
