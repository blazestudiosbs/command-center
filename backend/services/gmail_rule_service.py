import re
import uuid
from datetime import datetime, timezone
from email.utils import parseaddr

import requests

from services import agent_permission_service, gmail_service
from storage import connection


EMAIL_PATTERN = r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_rule_request(content: str) -> dict | None:
    if not re.search(r"\b(permanently delete(?:d)?|delete(?:d)? permanently|permanent(?:ly)? deletion)\b", content, re.I):
        return None
    match = re.search(EMAIL_PATTERN, content, re.I)
    if not match:
        return None
    sender = parseaddr(match.group(0))[1].strip().lower()
    return {"sender": sender, "action": "permanent_delete", "match_existing": True}


def _query(sender: str) -> str:
    return f"from:({sender})"


def _count_matches(user_id: str, sender: str) -> int:
    token = gmail_service._access_token(user_id)
    response = requests.get(
        gmail_service.MESSAGES_URL,
        headers={"Authorization": f"Bearer {token}"},
        params={"q": _query(sender), "maxResults": 1, "includeSpamTrash": "true"},
        timeout=15,
    )
    response.raise_for_status()
    return max(0, int(response.json().get("resultSizeEstimate") or len(response.json().get("messages") or [])))


def propose(user_id: str, sender: str, *, source: str) -> dict:
    agent_permission_service.require(user_id, "gmail", "search")
    if not gmail_service.get_status(user_id)["connected"]:
        raise RuntimeError("Gmail is not connected to Vera.")
    address = parseaddr(sender)[1].strip().lower()
    if not re.fullmatch(EMAIL_PATTERN, address, re.I):
        raise ValueError("An exact sender email address is required.")
    count = _count_matches(user_id, address)
    now = _now()
    rule_id = str(uuid.uuid4())
    note = f"Validated exact-sender Gmail query {_query(address)}; approximately {count} existing messages match."
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO gmail_automation_rules
                (id,user_id,sender,action,status,match_existing,validation_match_count,validation_note,created_source,created_utc)
            VALUES (?, ?, ?, 'permanent_delete', 'pending', 1, ?, ?, ?, ?)
            ON CONFLICT(user_id,sender,action) DO UPDATE SET
                status = 'pending', validation_match_count = excluded.validation_match_count,
                validation_note = excluded.validation_note, created_source = excluded.created_source,
                created_utc = excluded.created_utc, decided_utc = NULL
            """,
            (rule_id, user_id, address, count, note, source[:50], now),
        )
        row = conn.execute(
            "SELECT * FROM gmail_automation_rules WHERE user_id = ? AND sender = ? AND action = 'permanent_delete'",
            (user_id, address),
        ).fetchone()
    return _serialize(row)


def _serialize(row) -> dict:
    result = dict(row)
    result["match_existing"] = bool(result["match_existing"])
    return result


def list_rules(user_id: str) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM gmail_automation_rules WHERE user_id = ? ORDER BY created_utc DESC, id DESC",
            (user_id,),
        ).fetchall()
    return [_serialize(row) for row in rows]


def decide(user_id: str, rule_id: str, approve: bool) -> dict:
    if approve:
        agent_permission_service.require(user_id, "gmail", "permanent_delete")
        if not gmail_service.get_status(user_id).get("permanent_delete_authorized"):
            raise RuntimeError("Reconnect Gmail with permanent-delete access before approving this rule.")
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM gmail_automation_rules WHERE id = ? AND user_id = ? AND status = 'pending'",
            (rule_id, user_id),
        ).fetchone()
        if not row:
            raise ValueError("Pending Gmail rule not found.")
        conn.execute(
            "UPDATE gmail_automation_rules SET status = ?, decided_utc = ? WHERE id = ?",
            ("active" if approve else "rejected", _now(), rule_id),
        )
        updated = conn.execute("SELECT * FROM gmail_automation_rules WHERE id = ?", (rule_id,)).fetchone()
    return _serialize(updated)


def run_active_rules(user_id: str, limit_per_rule: int = 100) -> dict:
    if not agent_permission_service.is_allowed(user_id, "gmail", "permanent_delete"):
        return {"status": "permission_off", "deleted": 0}
    if not gmail_service.get_status(user_id).get("permanent_delete_authorized"):
        return {"status": "authorization_missing", "deleted": 0}
    token = gmail_service._access_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    deleted = 0
    with connection() as conn:
        rules = conn.execute(
            "SELECT * FROM gmail_automation_rules WHERE user_id = ? AND status = 'active'",
            (user_id,),
        ).fetchall()
    for rule in rules:
        listing = requests.get(
            gmail_service.MESSAGES_URL, headers=headers,
            params={"q": _query(rule["sender"]), "maxResults": max(1, min(limit_per_rule, 100)), "includeSpamTrash": "true"}, timeout=15,
        )
        listing.raise_for_status()
        rule_deleted = 0
        for item in listing.json().get("messages") or []:
            metadata = gmail_service._message_metadata(token, item["id"])
            actual_sender = parseaddr(metadata["sender"])[1].strip().lower()
            if actual_sender != rule["sender"]:
                continue
            response = requests.delete(f"{gmail_service.MESSAGES_URL}/{item['id']}", headers=headers, timeout=10)
            response.raise_for_status()
            rule_deleted += 1
        with connection() as conn:
            conn.execute(
                "UPDATE gmail_automation_rules SET last_run_utc = ?, deleted_count = deleted_count + ? WHERE id = ?",
                (_now(), rule_deleted, rule["id"]),
            )
        deleted += rule_deleted
    return {"status": "completed", "deleted": deleted}
