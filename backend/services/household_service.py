import hashlib
import hmac
import os
import uuid
from pathlib import Path

from storage import connection


class UnlinkedVoiceIdentityError(PermissionError):
    pass


def _utc_sql() -> str:
    return "strftime('%Y-%m-%dT%H:%M:%fZ','now')"


def ensure_owner_member() -> dict:
    with connection() as conn:
        owner = conn.execute("SELECT id,username FROM users WHERE id='owner' AND active=1").fetchone()
        if not owner:
            raise RuntimeError("The household owner account is unavailable.")
        conn.execute(
            f"""
            INSERT INTO household_members (id,user_id,display_name,role,status,created_utc,updated_utc)
            VALUES ('owner',?,?, 'owner','active',{_utc_sql()},{_utc_sql()})
            ON CONFLICT(id) DO UPDATE SET user_id=excluded.user_id,updated_utc=excluded.updated_utc
            """,
            (owner["id"], owner["username"]),
        )
        row = conn.execute("SELECT * FROM household_members WHERE id='owner'").fetchone()
    return dict(row)


def list_members() -> list[dict]:
    ensure_owner_member()
    with connection() as conn:
        rows = conn.execute(
            "SELECT id,user_id,display_name,role,status,created_utc,updated_utc FROM household_members ORDER BY CASE role WHEN 'owner' THEN 0 WHEN 'adult' THEN 1 WHEN 'child' THEN 2 ELSE 3 END, display_name"
        ).fetchall()
    return [dict(row) for row in rows]


def _identity_key() -> bytes:
    path = Path(os.getenv("VERA_IDENTITY_HASH_KEY_FILE", os.getenv("VERA_ALEXA_RELAY_SECRET_FILE", "/run/secrets/alexa_relay_secret")))
    try:
        key = path.read_bytes().strip()
    except OSError as exc:
        raise RuntimeError("Household identity hashing is not configured.") from exc
    if len(key) < 32:
        raise RuntimeError("Household identity hashing is not configured safely.")
    return key


def subject_hash(provider: str, subject_id: str) -> str:
    normalized_provider = provider.strip().lower()
    cleaned_subject = subject_id.strip()
    if not normalized_provider or not cleaned_subject:
        raise ValueError("Voice provider and subject are required.")
    return hmac.new(_identity_key(), f"voice:{normalized_provider}:{cleaned_subject}".encode(), hashlib.sha256).hexdigest()


def link_voice_identity(*, member_id: str, provider: str, subject_id: str) -> dict:
    ensure_owner_member()
    normalized_provider = provider.strip().lower()
    hashed = subject_hash(normalized_provider, subject_id)
    with connection() as conn:
        member = conn.execute("SELECT * FROM household_members WHERE id=? AND status='active'", (member_id,)).fetchone()
        if not member:
            raise ValueError("That household member is unavailable.")
        if not member["user_id"]:
            raise ValueError("That household member does not have a private Vera account yet.")
        identity_id = str(uuid.uuid4())
        conn.execute(
            f"""
            INSERT INTO household_voice_identities (id,household_member_id,provider,subject_hash,created_utc,updated_utc)
            VALUES (?,?,?,?,{_utc_sql()},{_utc_sql()})
            ON CONFLICT(provider,subject_hash) DO UPDATE SET
                household_member_id=excluded.household_member_id,
                updated_utc=excluded.updated_utc
            """,
            (identity_id, member_id, normalized_provider, hashed),
        )
        row = conn.execute(
            "SELECT id,household_member_id,provider,created_utc,updated_utc FROM household_voice_identities WHERE provider=? AND subject_hash=?",
            (normalized_provider, hashed),
        ).fetchone()
    return dict(row)


def resolve_voice_identity(*, provider: str, subject_id: str) -> dict:
    ensure_owner_member()
    hashed = subject_hash(provider, subject_id)
    with connection() as conn:
        row = conn.execute(
            """
            SELECT hm.id AS member_id,hm.user_id,hm.display_name,hm.role
            FROM household_voice_identities hvi
            JOIN household_members hm ON hm.id=hvi.household_member_id
            JOIN users u ON u.id=hm.user_id
            WHERE hvi.provider=? AND hvi.subject_hash=? AND hm.status='active' AND u.active=1
            """,
            (provider.strip().lower(), hashed),
        ).fetchone()
    if not row:
        raise UnlinkedVoiceIdentityError("This Echo identity is not linked to a household member.")
    return dict(row)
