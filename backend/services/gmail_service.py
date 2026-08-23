import json
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from pathlib import Path
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet, InvalidToken

from storage import connection


GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
GMAIL_FULL_SCOPE = "https://mail.google.com/"
CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
CATEGORIES = (
    "Accounts/Passwords", "Accounts/Verification", "Accounts/Security",
    "Financial/Taxes", "Financial/Banking", "Financial/Payments", "Financial/Bills",
    "Shopping/Shipping", "Shopping/Receipts", "Shopping/Orders", "Shopping/Promotions",
    "Travel/Flights", "Travel/Hotels", "Travel/Reservations",
    "Personal/Family", "Personal/Medical", "Personal/Education",
    "Subscriptions/Entertainment", "Subscriptions/Newsletters", "Needs Review",
)
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
LABELS_URL = "https://gmail.googleapis.com/gmail/v1/users/me/labels"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _secret(env_name: str, file_env_name: str, default_path: str) -> str:
    direct = os.getenv(env_name, "").strip()
    if direct:
        return direct
    path = Path(os.getenv(file_env_name, default_path))
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _config() -> dict:
    return {
        "client_id": os.getenv("GMAIL_CLIENT_ID", "").strip(),
        "client_secret": _secret(
            "GMAIL_CLIENT_SECRET", "GMAIL_CLIENT_SECRET_FILE", "/run/secrets/gmail_client_secret"
        ),
        "redirect_uri": os.getenv("GMAIL_OAUTH_REDIRECT_URI", "").strip(),
        "encryption_key": _secret(
            "VERA_TOKEN_ENCRYPTION_KEY", "VERA_TOKEN_ENCRYPTION_KEY_FILE", "/run/secrets/vera_token_encryption_key"
        ),
    }


def _fernet() -> Fernet:
    key = _config()["encryption_key"]
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError("Vera token encryption is not configured correctly.") from exc


def configured() -> bool:
    config = _config()
    if not all(config.values()):
        return False
    try:
        _fernet()
        return config["redirect_uri"].startswith("https://")
    except RuntimeError:
        return False


def get_status(user_id: str) -> dict:
    with connection() as conn:
        row = conn.execute(
            "SELECT email_address, scopes_json, connected_utc, updated_utc FROM gmail_connections WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    is_configured = configured()
    is_connected = row is not None
    scopes = json.loads(row["scopes_json"]) if row else [GMAIL_MODIFY_SCOPE]
    return {
        "provider": "gmail",
        "configured": is_configured,
        "connected": is_connected,
        "status": "connected" if is_connected else ("ready_to_connect" if is_configured else "not_configured"),
        "email_address": row["email_address"] if row else None,
        "scopes": scopes,
        "organizer_authorized": bool(row and (GMAIL_MODIFY_SCOPE in scopes or GMAIL_FULL_SCOPE in scopes)),
        "permanent_delete_authorized": bool(row and GMAIL_FULL_SCOPE in scopes),
        "access": "read_only",
        "can_send": False,
        "can_modify": False,
        "connected_utc": row["connected_utc"] if row else None,
        "detail": (
            "Gmail is connected with read-only access."
            if is_connected
            else "Gmail OAuth is ready for authorization."
            if is_configured
            else "Gmail OAuth credentials and token encryption must be configured."
        ),
    }


def authorization_url(user_id: str, *, permanent_delete: bool = False, calendar_read: bool = False) -> str:
    if not configured():
        raise RuntimeError("Gmail OAuth is not configured.")
    config = _config()
    state = secrets.token_urlsafe(32)
    now = _utc_now()
    with connection() as conn:
        conn.execute("DELETE FROM gmail_oauth_states WHERE expires_utc < ?", (_iso(now),))
        conn.execute(
            "INSERT INTO gmail_oauth_states (state, user_id, expires_utc, created_utc) VALUES (?, ?, ?, ?)",
            (state, user_id, _iso(now + timedelta(minutes=10)), _iso(now)),
        )
    scopes = [GMAIL_FULL_SCOPE if permanent_delete else GMAIL_MODIFY_SCOPE]
    if calendar_read:
        scopes.append(CALENDAR_READONLY_SCOPE)
    return AUTH_URL + "?" + urlencode(
        {
            "client_id": config["client_id"],
            "redirect_uri": config["redirect_uri"],
            "response_type": "code",
            "scope": " ".join(scopes),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
    )


def complete_authorization(state: str, code: str) -> dict:
    now = _utc_now()
    with connection() as conn:
        row = conn.execute("SELECT * FROM gmail_oauth_states WHERE state = ?", (state,)).fetchone()
        if not row or row["expires_utc"] < _iso(now):
            raise ValueError("Gmail authorization state is invalid or expired.")
        conn.execute("DELETE FROM gmail_oauth_states WHERE state = ?", (state,))
    config = _config()
    response = requests.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "redirect_uri": config["redirect_uri"],
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    response.raise_for_status()
    tokens = response.json()
    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")
    if not refresh_token or not access_token:
        raise RuntimeError("Google did not return the required Gmail tokens.")
    profile = requests.get(
        PROFILE_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    profile.raise_for_status()
    email_address = profile.json().get("emailAddress", "").strip()
    if not email_address:
        raise RuntimeError("Google did not return the Gmail account address.")
    scopes = tokens.get("scope", GMAIL_READONLY_SCOPE).split()
    encrypted = _fernet().encrypt(refresh_token.encode("utf-8")).decode("ascii")
    timestamp = _iso(now)
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO gmail_connections
                (user_id, email_address, encrypted_refresh_token, scopes_json, connected_utc, updated_utc)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                email_address = excluded.email_address,
                encrypted_refresh_token = excluded.encrypted_refresh_token,
                scopes_json = excluded.scopes_json,
                updated_utc = excluded.updated_utc
            """,
            (row["user_id"], email_address, encrypted, json.dumps(scopes), timestamp, timestamp),
        )
    return {**get_status(row["user_id"]), "_user_id": row["user_id"]}


def disconnect(user_id: str) -> dict:
    with connection() as conn:
        row = conn.execute(
            "SELECT encrypted_refresh_token FROM gmail_connections WHERE user_id = ?", (user_id,)
        ).fetchone()
        conn.execute("DELETE FROM gmail_connections WHERE user_id = ?", (user_id,))
    revoked = False
    if row:
        try:
            token = _fernet().decrypt(row["encrypted_refresh_token"].encode("ascii")).decode("utf-8")
            response = requests.post(REVOKE_URL, data={"token": token}, timeout=10)
            revoked = response.status_code == 200
        except (InvalidToken, RuntimeError, requests.RequestException):
            revoked = False
    return {"disconnected": True, "google_access_revoked": revoked}


def _access_token(user_id: str) -> str:
    with connection() as conn:
        row = conn.execute(
            "SELECT encrypted_refresh_token FROM gmail_connections WHERE user_id = ?", (user_id,)
        ).fetchone()
    if not row:
        raise RuntimeError("Gmail is not connected.")
    try:
        refresh_token = _fernet().decrypt(
            row["encrypted_refresh_token"].encode("ascii")
        ).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("The stored Gmail authorization cannot be decrypted.") from exc
    config = _config()
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    response.raise_for_status()
    access_token = response.json().get("access_token")
    if not access_token:
        raise RuntimeError("Google did not return a Gmail access token.")
    return access_token


def _safe_label(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[\x00-\x1f/]+", "-", value).strip(" .-")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned or fallback)[:80]


def _learned_category(user_id: str, sender: str) -> str | None:
    _display_name, email_address = parseaddr(sender)
    normalized_sender = email_address.strip().lower()
    domain = normalized_sender.partition("@")[2]
    with connection() as conn:
        row = conn.execute(
            """
            SELECT category FROM gmail_classification_rules
            WHERE user_id = ? AND approved = 1
              AND ((match_type = 'sender' AND match_value = ?)
                OR (match_type = 'domain' AND match_value = ?))
            ORDER BY CASE match_type WHEN 'sender' THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (user_id, normalized_sender, domain),
        ).fetchone()
    return row["category"] if row else None


def _classification(sender: str, subject: str, user_id: str | None = None) -> tuple[str, str]:
    learned = _learned_category(user_id, sender) if user_id else None
    if learned:
        return learned, "learned"
    text = f"{sender} {subject}".lower()
    rules = (
        ("Accounts/Passwords", ("password reset", "change your password", "password changed")),
        ("Accounts/Verification", ("verification code", "verify your", "confirm your email", "one-time code", "2fa")),
        ("Accounts/Security", ("security alert", "new login", "new sign-in", "suspicious", "unrecognized device")),
        ("Financial/Taxes", ("tax", "irs", "1099", "w-2", "w2 ", "tax return")),
        ("Financial/Banking", ("bank", "credit union", "account statement", "balance alert", "deposit")),
        ("Financial/Payments", ("payment received", "payment sent", "payment confirmation", "autopay", "paid")),
        ("Financial/Bills", ("bill", "invoice", "amount due", "due date", "utility statement")),
        ("Shopping/Shipping", ("shipped", "out for delivery", "delivered", "tracking number", "shipment")),
        ("Shopping/Receipts", ("receipt", "purchase confirmation", "thanks for your purchase")),
        ("Shopping/Orders", ("order confirmation", "your order", "order #", "amazon order")),
        ("Shopping/Promotions", ("sale", "coupon", "% off", "limited time", "special offer", "deal")),
        ("Travel/Flights", ("flight", "boarding pass", "airline", "departure gate")),
        ("Travel/Hotels", ("hotel", "check-in", "check out", "room reservation")),
        ("Travel/Reservations", ("reservation", "booking", "itinerary", "rental car")),
        ("Personal/Medical", ("appointment", "patient", "prescription", "pharmacy", "medical", "health portal")),
        ("Personal/Education", ("school", "teacher", "student", "classroom", "tuition", "course")),
        ("Subscriptions/Entertainment", ("netflix", "spotify", "streaming", "new episode", "watch now")),
        ("Subscriptions/Newsletters", ("newsletter", "digest", "weekly update", "unsubscribe")),
    )
    match = next((category for category, keywords in rules if any(word in text for word in keywords)), None)
    return (match, "high") if match else ("Needs Review", "low")


def learn_sender_rule(user_id: str, sender: str, category: str) -> dict:
    if category not in CATEGORIES:
        raise ValueError("Unsupported Gmail category.")
    _display_name, email_address = parseaddr(sender)
    normalized_sender = email_address.strip().lower()
    if not normalized_sender or "@" not in normalized_sender:
        raise ValueError("A valid sender email address is required.")
    now = _iso(_utc_now())
    rule_id = str(uuid.uuid4())
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO gmail_classification_rules
                (id, user_id, match_type, match_value, category, source, approved, created_utc, updated_utc)
            VALUES (?, ?, 'sender', ?, ?, 'user', 1, ?, ?)
            ON CONFLICT(user_id, match_type, match_value) DO UPDATE SET
                category = excluded.category, source = 'user', approved = 1,
                updated_utc = excluded.updated_utc
            """,
            (rule_id, user_id, normalized_sender, category, now, now),
        )
        row = conn.execute(
            "SELECT * FROM gmail_classification_rules WHERE user_id = ? AND match_type = 'sender' AND match_value = ?",
            (user_id, normalized_sender),
        ).fetchone()
    return {**dict(row), "approved": bool(row["approved"])}


def get_learning_status(user_id: str) -> dict:
    with connection() as conn:
        row = conn.execute("SELECT * FROM gmail_learning_settings WHERE user_id = ?", (user_id,)).fetchone()
        rule_count = conn.execute(
            "SELECT COUNT(*) FROM gmail_classification_rules WHERE user_id = ? AND approved = 1", (user_id,)
        ).fetchone()[0]
        if row is None:
            now = _iso(_utc_now())
            conn.execute(
                """
                INSERT INTO gmail_learning_settings
                    (user_id, cloud_review_enabled, monthly_budget_usd, weekly_message_limit, include_message_bodies, updated_utc)
                VALUES (?, 0, 0.25, 20, 0, ?)
                """,
                (user_id, now),
            )
    return {
        "learned_rule_count": rule_count,
        "cloud_review_enabled": bool(row["cloud_review_enabled"]) if row else False,
        "monthly_budget_usd": row["monthly_budget_usd"] if row else 0.25,
        "weekly_message_limit": row["weekly_message_limit"] if row else 20,
        "include_message_bodies": bool(row["include_message_bodies"]) if row else False,
        "detail": "Cloud review is staged but remains off until local learning is verified.",
    }


def organizer_preview(user_id: str, limit: int = 20) -> dict:
    safe_limit = max(1, min(int(limit), 50))
    access_token = _access_token(user_id)
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(
        MESSAGES_URL,
        headers=headers,
        params={"labelIds": "INBOX", "maxResults": safe_limit, "includeSpamTrash": "false"},
        timeout=15,
    )
    response.raise_for_status()
    messages = response.json().get("messages") or []
    proposals = []
    for item in messages[:safe_limit]:
        detail = requests.get(
            f"{MESSAGES_URL}/{item['id']}",
            headers=headers,
            params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
            timeout=10,
        )
        detail.raise_for_status()
        payload = detail.json()
        header_values = {
            header.get("name", "").lower(): header.get("value", "")
            for header in payload.get("payload", {}).get("headers", [])
        }
        sender_raw = header_values.get("from", "Unknown sender")
        display_name, email_address = parseaddr(sender_raw)
        sender_name = _safe_label(display_name or email_address, "Unknown sender")
        category, confidence = _classification(sender_raw, header_values.get("subject", ""), user_id)
        category_label = f"Vera/{category}"
        proposals.append(
            {
                "message_id": item["id"],
                "sender": sender_raw,
                "subject": header_values.get("subject") or "(no subject)",
                "date": header_values.get("date"),
                "category": category,
                "confidence": confidence,
                "labels": [category_label, f"Vera/Senders/{sender_name}"],
                "remove_from_inbox": True,
                "simulation": True,
            }
        )
    return {
        "mode": "simulation",
        "cloud_processing": False,
        "message_count": len(proposals),
        "messages": proposals,
        "detail": "No Gmail messages or labels were changed.",
    }


def get_organizer_settings(user_id: str) -> dict:
    with connection() as conn:
        row = conn.execute("SELECT * FROM gmail_organizer_settings WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO gmail_organizer_settings (user_id, enabled, poll_interval_seconds, updated_utc) VALUES (?, 0, 300, ?)",
                (user_id, _iso(_utc_now())),
            )
    return {
        "enabled": bool(row["enabled"]) if row else False,
        "poll_interval_seconds": row["poll_interval_seconds"] if row else 300,
        "enabled_utc": row["enabled_utc"] if row else None,
        "filing_mode": "apply_labels_then_remove_inbox",
    }


def set_organizer_enabled(user_id: str, enabled: bool) -> dict:
    status = get_status(user_id)
    if enabled and not status["organizer_authorized"]:
        raise RuntimeError("Reconnect Gmail to approve organizer access first.")
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO gmail_organizer_settings (user_id, enabled, poll_interval_seconds, enabled_utc, updated_utc)
            VALUES (?, ?, 300, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                enabled = excluded.enabled,
                enabled_utc = CASE WHEN excluded.enabled = 1 AND gmail_organizer_settings.enabled = 0
                    THEN excluded.enabled_utc ELSE gmail_organizer_settings.enabled_utc END,
                updated_utc = excluded.updated_utc
            """,
            (user_id, int(enabled), _iso(_utc_now()) if enabled else None, _iso(_utc_now())),
        )
    return get_organizer_settings(user_id)


def _message_metadata(access_token: str, message_id: str) -> dict:
    response = requests.get(
        f"{MESSAGES_URL}/{message_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    headers = {item.get("name", "").lower(): item.get("value", "") for item in payload.get("payload", {}).get("headers", [])}
    return {"sender": headers.get("from", "Unknown sender"), "subject": headers.get("subject", "(no subject)")}


def _label_ids(access_token: str, names: list[str]) -> list[str]:
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(LABELS_URL, headers=headers, timeout=10)
    response.raise_for_status()
    existing = {item["name"]: item["id"] for item in response.json().get("labels", [])}
    ids = []
    for name in names:
        if name not in existing:
            created = requests.post(
                LABELS_URL, headers=headers,
                json={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
                timeout=10,
            )
            created.raise_for_status()
            existing[name] = created.json()["id"]
        ids.append(existing[name])
    return ids


def run_organizer(user_id: str, limit: int = 100, include_existing: bool = False) -> dict:
    settings = get_organizer_settings(user_id)
    if not settings["enabled"]:
        return {"status": "disabled", "processed": 0, "failed": 0}
    access_token = _access_token(user_id)
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"labelIds": "INBOX", "maxResults": max(1, min(limit, 100)), "includeSpamTrash": "false"}
    if not include_existing and settings.get("enabled_utc"):
        enabled_epoch = int(datetime.fromisoformat(settings["enabled_utc"].replace("Z", "+00:00")).timestamp())
        params["q"] = f"after:{enabled_epoch}"
    listing = requests.get(
        MESSAGES_URL, headers=headers,
        params=params,
        timeout=15,
    )
    listing.raise_for_status()
    processed = failed = 0
    for item in listing.json().get("messages") or []:
        with connection() as conn:
            exists = conn.execute(
                "SELECT 1 FROM gmail_organizer_processed WHERE user_id = ? AND message_id = ?",
                (user_id, item["id"]),
            ).fetchone()
        if exists:
            continue
        try:
            metadata = _message_metadata(access_token, item["id"])
            category, _confidence = _classification(metadata["sender"], metadata["subject"], user_id)
            display, address = parseaddr(metadata["sender"])
            sender_name = _safe_label(display or address, "Unknown sender")
            labels = [f"Vera/{category}", f"Vera/Senders/{sender_name}"]
            ids = _label_ids(access_token, labels)
            modified = requests.post(
                f"{MESSAGES_URL}/{item['id']}/modify", headers=headers,
                json={"addLabelIds": ids, "removeLabelIds": ["INBOX"]}, timeout=10,
            )
            modified.raise_for_status()
            with connection() as conn:
                conn.execute(
                    "INSERT INTO gmail_organizer_processed (user_id, message_id, category, labels_json, processed_utc) VALUES (?, ?, ?, ?, ?)",
                    (user_id, item["id"], category, json.dumps(labels), _iso(_utc_now())),
                )
            processed += 1
        except requests.RequestException:
            failed += 1
    return {"status": "completed", "processed": processed, "failed": failed}


def search_metadata(user_id: str, query: str, limit: int = 5) -> list[dict]:
    safe_limit = max(1, min(int(limit), 10))
    access_token = _access_token(user_id)
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(
        MESSAGES_URL,
        headers=headers,
        params={"q": query.strip(), "maxResults": safe_limit, "includeSpamTrash": "false"},
        timeout=15,
    )
    response.raise_for_status()
    results = []
    for item in (response.json().get("messages") or [])[:safe_limit]:
        metadata = _message_metadata(access_token, item["id"])
        results.append({"message_id": item["id"], **metadata})
    return results
