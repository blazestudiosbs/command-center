import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone

from storage import connection


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _public(row):
    result = dict(row)
    result.pop("token_hash", None)
    result["enabled"] = bool(result["enabled"])
    result["status"] = json.loads(result.pop("status_json") or "null")
    if not result["enabled"]:
        result["connection_status"] = "disabled"
    elif not result["last_seen_utc"]:
        result["connection_status"] = "awaiting_first_report"
    else:
        seen = datetime.fromisoformat(result["last_seen_utc"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - seen).total_seconds()
        result["connection_status"] = "online" if age <= 300 else "stale"
    return result


def list_servers(user_id):
    with connection() as conn:
        rows = conn.execute("SELECT * FROM managed_servers WHERE owner_user_id=? ORDER BY name COLLATE NOCASE", (user_id,)).fetchall()
    return [_public(row) for row in rows]


def register(user_id, *, name, hostname):
    name, hostname = name.strip(), hostname.strip().lower()
    if not name or not hostname:
        raise ValueError("Name and hostname are required.")
    token = secrets.token_urlsafe(32)
    server_id, now = str(uuid.uuid4()), _now()
    with connection() as conn:
        conn.execute(
            "INSERT INTO managed_servers (id,owner_user_id,name,hostname,token_hash,created_utc,updated_utc) VALUES (?,?,?,?,?,?,?)",
            (server_id, user_id, name, hostname, _hash(token), now, now),
        )
        row = conn.execute("SELECT * FROM managed_servers WHERE id=?", (server_id,)).fetchone()
    return {**_public(row), "enrollment_token": token}


def set_enabled(user_id, server_id, enabled):
    with connection() as conn:
        result = conn.execute("UPDATE managed_servers SET enabled=?,updated_utc=? WHERE id=? AND owner_user_id=?", (int(enabled), _now(), server_id, user_id))
        if result.rowcount != 1:
            raise LookupError("Server not found.")
        row = conn.execute("SELECT * FROM managed_servers WHERE id=?", (server_id,)).fetchone()
    return _public(row)


def rotate_token(user_id, server_id):
    token = secrets.token_urlsafe(32)
    with connection() as conn:
        result = conn.execute("UPDATE managed_servers SET token_hash=?,last_seen_utc=NULL,agent_version=NULL,status_json=NULL,updated_utc=? WHERE id=? AND owner_user_id=?", (_hash(token), _now(), server_id, user_id))
        if result.rowcount != 1:
            raise LookupError("Server not found.")
        row = conn.execute("SELECT * FROM managed_servers WHERE id=?", (server_id,)).fetchone()
    return {**_public(row), "enrollment_token": token}


def record_heartbeat(token, *, agent_version, status):
    with connection() as conn:
        row = conn.execute("SELECT * FROM managed_servers WHERE token_hash=?", (_hash(token),)).fetchone()
        if not row or not row["enabled"]:
            raise PermissionError("Invalid or disabled server token.")
        now = _now()
        conn.execute("UPDATE managed_servers SET last_seen_utc=?,agent_version=?,status_json=?,updated_utc=? WHERE id=?", (now, agent_version, json.dumps(status), now, row["id"]))
        updated = conn.execute("SELECT * FROM managed_servers WHERE id=?", (row["id"],)).fetchone()
    return _public(updated)
