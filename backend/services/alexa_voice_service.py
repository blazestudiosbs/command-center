import hashlib
import hmac
import os
import time
from pathlib import Path

from services import agent_permission_service, audit_service, conversation_service, household_service, vera_conversation_service
from storage import connection


MAX_CLOCK_SKEW_SECONDS = 60
MAX_SPOKEN_CHARS = 700


class AlexaRelayAuthenticationError(PermissionError):
    pass


def _secret() -> bytes:
    path = Path(os.getenv("VERA_ALEXA_RELAY_SECRET_FILE", "/run/secrets/alexa_relay_secret"))
    try:
        secret = path.read_bytes().strip()
    except OSError as exc:
        raise AlexaRelayAuthenticationError("Alexa relay authentication is not configured.") from exc
    if len(secret) < 32:
        raise AlexaRelayAuthenticationError("Alexa relay authentication is not configured safely.")
    return secret


def sign(timestamp: str, body: bytes, secret: bytes) -> str:
    return "sha256=" + hmac.new(secret, timestamp.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()


def authenticate(*, timestamp: str, signature: str, body: bytes, now: int | None = None) -> None:
    try:
        sent_at = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise AlexaRelayAuthenticationError("Invalid relay timestamp.") from exc
    current = int(time.time()) if now is None else int(now)
    if abs(current - sent_at) > MAX_CLOCK_SKEW_SECONDS:
        raise AlexaRelayAuthenticationError("Expired relay request.")
    if not hmac.compare_digest(signature, sign(timestamp, body, _secret())):
        raise AlexaRelayAuthenticationError("Invalid relay signature.")


def _conversation(user_id: str, member_id: str, session_id: str) -> str:
    with connection() as conn:
        row = conn.execute(
            "SELECT conversation_id FROM alexa_voice_sessions WHERE session_id=? AND user_id=? AND household_member_id=?",
            (session_id, user_id, member_id),
        ).fetchone()
    if row and conversation_service.get_conversation(row["conversation_id"], user_id):
        with connection() as conn:
            conn.execute(
                "UPDATE alexa_voice_sessions SET updated_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE session_id=?",
                (session_id,),
            )
        return row["conversation_id"]
    conversation = conversation_service.create_conversation(user_id, "Alexa · Vera")
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO alexa_voice_sessions (session_id,user_id,conversation_id,household_member_id,created_utc,updated_utc)
            VALUES (?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            ON CONFLICT(session_id) DO UPDATE SET
                user_id=excluded.user_id,
                conversation_id=excluded.conversation_id,
                household_member_id=excluded.household_member_id,
                updated_utc=excluded.updated_utc
            """,
            (session_id, user_id, conversation["id"], member_id),
        )
    return conversation["id"]


def _spoken(text: str) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= MAX_SPOKEN_CHARS:
        return cleaned
    shortened = cleaned[: MAX_SPOKEN_CHARS - 1].rsplit(" ", 1)[0]
    return shortened + "…"


def respond(*, provider: str, subject_id: str, session_id: str, request_id: str, text: str) -> dict:
    identity = household_service.resolve_voice_identity(provider=provider, subject_id=subject_id)
    user_id = identity["user_id"]
    agent_permission_service.require(user_id, "alexa_voice", "receive_voice")
    conversation_id = _conversation(user_id, identity["member_id"], session_id)
    result = vera_conversation_service.respond(
        owner_user_id=user_id,
        conversation_id=conversation_id,
        content=text,
        client_message_id=f"alexa:{request_id}",
        source="alexa",
    )
    assistant = result.get("assistant_message")
    if assistant is None:
        messages = conversation_service.list_messages(conversation_id, user_id)
        assistant = next((item for item in reversed(messages) if item["role"] == "assistant"), None)
    spoken = _spoken(assistant["content"] if assistant else "I already handled that request.")
    audit_service.append_event(
        actor_user_id=user_id,
        action="alexa.voice_response",
        resource_type="conversation",
        resource_id=conversation_id,
        request_id=request_id,
        outcome="succeeded",
        details={"source": "alexa", "household_member_id": identity["member_id"], "session_id_hash": hashlib.sha256(session_id.encode()).hexdigest()[:16]},
    )
    return {"text": spoken, "conversation_id": conversation_id, "duplicate": bool(result.get("duplicate"))}
