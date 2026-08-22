import os

import requests


def send(title: str, message: str, severity: str = "info") -> dict:
    webhook = os.getenv("DISCORD_WEBHOOK", "").strip()
    if not webhook:
        return {"sent": False, "error": "DISCORD_WEBHOOK is not configured."}

    icon = {
        "info": "ℹ️",
        "warning": "⚠️",
        "critical": "🚨",
        "success": "✅",
    }.get(severity, "ℹ️")
    try:
        response = requests.post(
            webhook,
            json={"content": f"{icon} **Command Center Alert**\n\n**{title}**\n{message}"},
            timeout=10,
        )
        return {
            "sent": response.status_code in {200, 204},
            "status_code": response.status_code,
            "response": response.text,
        }
    except Exception as exc:
        return {"sent": False, "error": str(exc)}
