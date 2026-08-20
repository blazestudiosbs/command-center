import os
from functools import lru_cache
from typing import Optional

from openai import OpenAI


DEFAULT_MODEL = "gpt-4.1-mini"


def _api_key() -> Optional[str]:
    value = os.getenv("OPENAI_API_KEY", "").strip()
    return value or None


def is_configured() -> bool:
    return _api_key() is not None


def get_status() -> dict:
    configured = is_configured()
    return {
        "provider": "openai",
        "configured": configured,
        "status": "configured" if configured else "not_configured",
        "connection_status": "not_checked" if configured else "disabled",
        "model": os.getenv("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        "detail": (
            "OpenAI API credentials are configured; connectivity has not been checked."
            if configured
            else "OPENAI_API_KEY is not configured; cloud requests are disabled."
        ),
    }


@lru_cache(maxsize=1)
def get_client() -> Optional[OpenAI]:
    api_key = _api_key()
    if api_key is None:
        return None
    return OpenAI(api_key=api_key, timeout=30.0, max_retries=1)


def get_model() -> str:
    return get_status()["model"]
