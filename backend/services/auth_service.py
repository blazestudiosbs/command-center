import base64
import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from storage import connection


OWNER_ID = "owner"
DEFAULT_OWNER_USERNAME = "bruce"
SESSION_HOURS = 12
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_encode(salt)}${_encode(derived)}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded_hash.split("$", 5)
        if algorithm != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
        )
        return hmac.compare_digest(derived, _decode(expected))
    except (ValueError, TypeError):
        return False


def owner_username() -> str:
    return os.getenv("VERA_ADMIN_USERNAME", DEFAULT_OWNER_USERNAME).strip() or DEFAULT_OWNER_USERNAME


def configured_password_hash() -> Optional[str]:
    value = os.getenv("VERA_ADMIN_PASSWORD_HASH", "").strip()
    return value or None


def sync_owner() -> bool:
    password_hash = configured_password_hash()
    if not password_hash:
        return False

    now = _format_utc(_utc_now())
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, username, password_hash, role, active, created_utc, updated_utc)
            VALUES (?, ?, ?, 'owner', 1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = excluded.username,
                password_hash = excluded.password_hash,
                active = 1,
                updated_utc = excluded.updated_utc
            """,
            (OWNER_ID, owner_username(), password_hash, now, now),
        )
    return True


def authenticate(username: str, password: str) -> Optional[dict[str, Any]]:
    if not sync_owner():
        return None
    with connection() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, role, active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if not row or not row["active"] or not verify_password(password, row["password_hash"]):
        return None
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: str) -> dict[str, Any]:
    now = _utc_now()
    expires = now + timedelta(hours=SESSION_HOURS)
    token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    with connection() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_utc <= ?", (_format_utc(now),))
        conn.execute(
            """
            INSERT INTO sessions
                (id, user_id, token_hash, csrf_token, created_utc, expires_utc, last_seen_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                user_id,
                _token_hash(token),
                csrf_token,
                _format_utc(now),
                _format_utc(expires),
                _format_utc(now),
            ),
        )
    return {"token": token, "csrf_token": csrf_token, "expires_utc": _format_utc(expires)}


def get_session(token: str) -> Optional[dict[str, Any]]:
    if not token:
        return None
    now = _format_utc(_utc_now())
    with connection() as conn:
        row = conn.execute(
            """
            SELECT s.id AS session_id, s.csrf_token, s.expires_utc,
                   u.id AS user_id, u.username, u.role, u.active
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.expires_utc > ?
            """,
            (_token_hash(token), now),
        ).fetchone()
        if not row or not row["active"]:
            return None
        conn.execute(
            "UPDATE sessions SET last_seen_utc = ? WHERE id = ?",
            (now, row["session_id"]),
        )
    return dict(row)


def delete_session(token: str) -> None:
    if not token:
        return
    with connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
