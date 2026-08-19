import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from storage import connection


ROLES = {"user", "assistant", "system"}
MESSAGE_STATUSES = {"pending", "complete", "failed"}


class ConversationNotFoundError(LookupError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _conversation_from_row(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "owner_user_id": row["owner_user_id"],
        "title": row["title"],
        "archived": bool(row["archived"]),
        "created_utc": row["created_utc"],
        "updated_utc": row["updated_utc"],
    }


def _message_from_row(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "conversation_id": row["conversation_id"],
        "role": row["role"],
        "content": row["content"],
        "sequence": row["sequence"],
        "client_message_id": row["client_message_id"],
        "status": row["status"],
        "model": row["model"],
        "metadata": json.loads(row["metadata_json"]),
        "created_utc": row["created_utc"],
    }


def create_conversation(owner_user_id: str, title: str = "New conversation") -> dict[str, Any]:
    now = _utc_now()
    conversation = {
        "id": str(uuid.uuid4()),
        "owner_user_id": owner_user_id,
        "title": title.strip()[:200] or "New conversation",
        "archived": False,
        "created_utc": now,
        "updated_utc": now,
    }
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO conversations
                (id, owner_user_id, title, archived, created_utc, updated_utc)
            VALUES (?, ?, ?, 0, ?, ?)
            """,
            (
                conversation["id"],
                owner_user_id,
                conversation["title"],
                now,
                now,
            ),
        )
    return conversation


def list_conversations(owner_user_id: str, include_archived: bool = False) -> list[dict[str, Any]]:
    query = "SELECT * FROM conversations WHERE owner_user_id = ?"
    parameters: list[Any] = [owner_user_id]
    if not include_archived:
        query += " AND archived = 0"
    query += " ORDER BY updated_utc DESC, id DESC"
    with connection() as conn:
        rows = conn.execute(query, parameters).fetchall()
    return [_conversation_from_row(row) for row in rows]


def get_conversation(conversation_id: str, owner_user_id: str) -> Optional[dict[str, Any]]:
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ? AND owner_user_id = ?",
            (conversation_id, owner_user_id),
        ).fetchone()
    return _conversation_from_row(row) if row else None


def list_messages(conversation_id: str, owner_user_id: str) -> list[dict[str, Any]]:
    if not get_conversation(conversation_id, owner_user_id):
        raise ConversationNotFoundError(conversation_id)
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY sequence",
            (conversation_id,),
        ).fetchall()
    return [_message_from_row(row) for row in rows]


def add_message(
    *,
    conversation_id: str,
    owner_user_id: str,
    role: str,
    content: str,
    client_message_id: Optional[str] = None,
    status: str = "complete",
    model: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if role not in ROLES:
        raise ValueError("Unsupported message role.")
    if status not in MESSAGE_STATUSES:
        raise ValueError("Unsupported message status.")
    cleaned_content = content.strip()
    if not cleaned_content:
        raise ValueError("Message content is required.")

    now = _utc_now()
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conversation = conn.execute(
            "SELECT id FROM conversations WHERE id = ? AND owner_user_id = ?",
            (conversation_id, owner_user_id),
        ).fetchone()
        if not conversation:
            raise ConversationNotFoundError(conversation_id)

        if client_message_id:
            existing = conn.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id = ? AND client_message_id = ?
                """,
                (conversation_id, client_message_id),
            ).fetchone()
            if existing:
                return _message_from_row(existing)

        sequence = conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()[0]
        message_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO messages
                (id, conversation_id, role, content, sequence, client_message_id,
                 status, model, metadata_json, created_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                conversation_id,
                role,
                cleaned_content,
                sequence,
                client_message_id,
                status,
                model,
                json.dumps(metadata or {}, separators=(",", ":"), default=str),
                now,
            ),
        )
        conn.execute(
            "UPDATE conversations SET updated_utc = ? WHERE id = ?",
            (now, conversation_id),
        )
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    return _message_from_row(row)
