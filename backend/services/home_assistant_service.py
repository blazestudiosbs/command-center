import os
from urllib.parse import urlparse

import requests


def _config() -> tuple[str | None, str | None]:
    url = os.getenv("HOME_ASSISTANT_URL", "").strip().rstrip("/")
    token = os.getenv("HOME_ASSISTANT_TOKEN", "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        url = ""
    return (url or None, token or None)


def get_status(*, check_connection: bool = False) -> dict:
    url, token = _config()
    configured = bool(url and token)
    result = {
        "provider": "home_assistant",
        "configured": configured,
        "status": "configured" if configured else "not_configured",
        "connection_status": "not_checked" if configured else "disabled",
        "detail": (
            "Home Assistant credentials are configured; connectivity has not been checked."
            if configured
            else "HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN are required."
        ),
    }
    if not configured or not check_connection:
        return result
    try:
        response = requests.get(
            f"{url}/api/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        response.raise_for_status()
        return {**result, "status": "online", "connection_status": "connected", "detail": "Home Assistant is reachable."}
    except requests.RequestException:
        return {**result, "status": "offline", "connection_status": "failed", "detail": "Home Assistant could not be reached."}


def get_overview(limit: int = 250) -> dict:
    url, token = _config()
    status = get_status(check_connection=True)
    if status["connection_status"] != "connected":
        return {"status": status, "entities": []}
    try:
        response = requests.get(
            f"{url}/api/states",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return {
            "status": {**status, "status": "offline", "connection_status": "failed", "detail": "Home Assistant states could not be read."},
            "entities": [],
        }
    entities = []
    for item in payload[:max(1, min(int(limit), 500))] if isinstance(payload, list) else []:
        attributes = item.get("attributes") if isinstance(item, dict) else {}
        attributes = attributes if isinstance(attributes, dict) else {}
        entity_id = str(item.get("entity_id", ""))
        if not entity_id:
            continue
        entities.append({
            "entity_id": entity_id,
            "domain": entity_id.partition(".")[0],
            "name": str(attributes.get("friendly_name") or entity_id),
            "state": str(item.get("state", "unknown")),
            "unit": attributes.get("unit_of_measurement"),
            "device_class": attributes.get("device_class"),
            "last_changed": item.get("last_changed"),
        })
    return {"status": status, "entities": entities}
