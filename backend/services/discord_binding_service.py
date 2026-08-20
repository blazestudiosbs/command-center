import uuid
from datetime import datetime, timezone

from services import conversation_service
from storage import connection


class DiscordIdentityDeniedError(PermissionError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_or_create(*, owner_user_id: str, guild_id: str, channel_id: str, discord_user_id: str) -> dict:
    now = _utc_now()
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT * FROM conversation_bindings
            WHERE provider = 'discord' AND external_scope_id = ? AND external_channel_id = ?
            """,
            (guild_id, channel_id),
        ).fetchone()
        if row:
            if row["external_user_id"] and row["external_user_id"] != discord_user_id:
                raise DiscordIdentityDeniedError("This Discord channel is paired to another user.")
            if not row["external_user_id"]:
                conn.execute(
                    "UPDATE conversation_bindings SET external_user_id = ?, updated_utc = ? WHERE id = ?",
                    (discord_user_id, now, row["id"]),
                )
            return dict(conn.execute("SELECT * FROM conversation_bindings WHERE id = ?", (row["id"],)).fetchone())

    conversation = conversation_service.create_conversation(owner_user_id, "Vera on Discord")
    binding_id = str(uuid.uuid4())
    try:
        with connection() as conn:
            conn.execute(
                """
                INSERT INTO conversation_bindings
                    (id, conversation_id, provider, external_scope_id, external_channel_id,
                     external_user_id, created_utc, updated_utc)
                VALUES (?, ?, 'discord', ?, ?, ?, ?, ?)
                """,
                (binding_id, conversation["id"], guild_id, channel_id, discord_user_id, now, now),
            )
    except Exception:
        with connection() as conn:
            conn.execute("DELETE FROM conversations WHERE id = ?", (conversation["id"],))
        raise
    return {
        "id": binding_id,
        "conversation_id": conversation["id"],
        "provider": "discord",
        "external_scope_id": guild_id,
        "external_channel_id": channel_id,
        "external_user_id": discord_user_id,
        "created_utc": now,
        "updated_utc": now,
    }
