import math
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from storage import connection


DEFAULT_MONTHLY_LIMIT_USD = 5.00
DEFAULT_DAILY_LIMIT_USD = 0.50
DEFAULT_PER_REQUEST_LIMIT_USD = 0.10
DEFAULT_INPUT_COST_PER_MILLION = 0.40
DEFAULT_OUTPUT_COST_PER_MILLION = 1.60


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def get_config() -> dict[str, Any]:
    return {
        "mode": "simulation",
        "currency": "USD",
        "limits": {
            "monthly_usd": _positive_float("VERA_BUDGET_MONTHLY_USD", DEFAULT_MONTHLY_LIMIT_USD),
            "daily_usd": _positive_float("VERA_BUDGET_DAILY_USD", DEFAULT_DAILY_LIMIT_USD),
            "per_request_usd": _positive_float(
                "VERA_BUDGET_PER_REQUEST_USD", DEFAULT_PER_REQUEST_LIMIT_USD
            ),
        },
        "pricing": {
            "input_per_million_tokens_usd": _positive_float(
                "VERA_OPENAI_INPUT_COST_PER_MILLION", DEFAULT_INPUT_COST_PER_MILLION
            ),
            "output_per_million_tokens_usd": _positive_float(
                "VERA_OPENAI_OUTPUT_COST_PER_MILLION", DEFAULT_OUTPUT_COST_PER_MILLION
            ),
        },
    }


def estimate_input_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    config = get_config()
    pricing = config["pricing"]
    cost = (
        max(0, input_tokens) * pricing["input_per_million_tokens_usd"]
        + max(0, output_tokens) * pricing["output_per_million_tokens_usd"]
    ) / 1_000_000
    return round(cost, 8)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _period_spend(now: datetime) -> dict[str, float]:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)
    with connection() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN created_utc >= ? THEN actual_cost_usd ELSE 0 END), 0) AS daily,
                COALESCE(SUM(CASE WHEN created_utc >= ? THEN actual_cost_usd ELSE 0 END), 0) AS monthly
            FROM budget_ledger
            WHERE mode = 'live' AND status = 'completed' AND actual_cost_usd IS NOT NULL
            """,
            (
                day_start.isoformat().replace("+00:00", "Z"),
                month_start.isoformat().replace("+00:00", "Z"),
            ),
        ).fetchone()
    return {"daily_usd": round(float(row["daily"]), 8), "monthly_usd": round(float(row["monthly"]), 8)}


def get_status() -> dict[str, Any]:
    config = get_config()
    spent = _period_spend(_utc_now())
    limits = config["limits"]
    return {
        **config,
        "spent": spent,
        "remaining": {
            "daily_usd": round(max(0.0, limits["daily_usd"] - spent["daily_usd"]), 8),
            "monthly_usd": round(max(0.0, limits["monthly_usd"] - spent["monthly_usd"]), 8),
        },
        "cloud_calls_enabled": False,
        "detail": "Budget decisions are simulated; this service does not make cloud requests.",
    }


def _decision(estimated_cost_usd: float, spent: dict[str, float], limits: dict[str, float]) -> tuple[str, str]:
    if estimated_cost_usd > limits["per_request_usd"]:
        return "block", "Estimated request cost exceeds the per-request limit."
    if spent["daily_usd"] + estimated_cost_usd > limits["daily_usd"]:
        return "block", "Estimated request cost would exceed the daily limit."
    if spent["monthly_usd"] + estimated_cost_usd > limits["monthly_usd"]:
        return "block", "Estimated request cost would exceed the monthly limit."
    return "allow", "Estimated request cost is within all configured limits."


def simulate(
    *,
    prompt: str,
    max_output_tokens: int,
    domain: str = "general",
    model: str = "gpt-4.1-mini",
    input_tokens: Optional[int] = None,
) -> dict[str, Any]:
    estimated_input_tokens = input_tokens if input_tokens is not None else estimate_input_tokens(prompt)
    estimated_input_tokens = max(0, int(estimated_input_tokens))
    estimated_output_tokens = max(0, int(max_output_tokens))
    estimated_cost_usd = estimate_cost(estimated_input_tokens, estimated_output_tokens)
    now = _utc_now()
    status = get_status()
    decision, reason = _decision(estimated_cost_usd, status["spent"], status["limits"])
    entry = {
        "id": str(uuid.uuid4()),
        "mode": "simulation",
        "domain": (domain or "general").strip() or "general",
        "model": (model or "gpt-4.1-mini").strip() or "gpt-4.1-mini",
        "input_tokens": estimated_input_tokens,
        "output_tokens": estimated_output_tokens,
        "estimated_cost_usd": estimated_cost_usd,
        "actual_cost_usd": None,
        "decision": decision,
        "reason": reason,
        "status": "simulated",
        "created_utc": now.isoformat().replace("+00:00", "Z"),
    }
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO budget_ledger
                (id, mode, domain, model, input_tokens, output_tokens,
                 estimated_cost_usd, actual_cost_usd, decision, reason, status, created_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["id"], entry["mode"], entry["domain"], entry["model"],
                entry["input_tokens"], entry["output_tokens"], entry["estimated_cost_usd"],
                entry["actual_cost_usd"], entry["decision"], entry["reason"],
                entry["status"], entry["created_utc"],
            ),
        )
    return {**entry, "limits": status["limits"], "spent": status["spent"]}


def list_ledger(limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 500))
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM budget_ledger ORDER BY created_utc DESC, id DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
    return [dict(row) for row in rows]
