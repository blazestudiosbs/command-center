from typing import Any, Optional

from services import budget_service, openai_service, policy_service, router_service


def run_guarded(
    *,
    input_data: Any,
    budget_text: str,
    max_output_tokens: int,
    domain: str = "general",
    instructions: Optional[str] = None,
):
    if not router_service.cloud_routing_enabled():
        raise RuntimeError("Cloud routing is disabled.")
    client = openai_service.get_client()
    if client is None:
        raise RuntimeError("OpenAI API key is not configured.")

    input_tokens = budget_service.estimate_live_input_tokens(budget_text)
    estimated_cost = budget_service.estimate_cost(input_tokens, max_output_tokens)
    policy = policy_service.evaluate_domain_request(
        domain=domain,
        provider="openai",
        model=openai_service.get_model(),
        estimated_cost_usd=estimated_cost,
    )
    if not policy["allowed"]:
        raise RuntimeError(policy["reason"])

    reservation = budget_service.reserve_live(
        prompt=budget_text,
        max_output_tokens=max_output_tokens,
        domain=domain,
        model=openai_service.get_model(),
    )
    request = {
        "model": openai_service.get_model(),
        "input": input_data,
        "max_output_tokens": max_output_tokens,
        "store": False,
    }
    if instructions:
        request["instructions"] = instructions
    try:
        response = client.responses.create(**request)
    except Exception as exc:
        budget_service.retain_live_reservation(reservation["id"], type(exc).__name__)
        raise

    status, incomplete_reason = openai_service.get_response_status(response)
    usage = getattr(response, "usage", None)
    settlement_reason = "Settled from API-reported token usage."
    if status != "completed":
        settlement_reason = (
            f"OpenAI response ended with status {status}"
            + (f": {incomplete_reason}." if incomplete_reason else ".")
        )
    if usage is None:
        budget_service.retain_live_reservation(
            reservation["id"], f"{settlement_reason} API usage was unavailable."
        )
        ledger = reservation
    else:
        ledger = budget_service.settle_live(
            reservation["id"],
            input_tokens=int(getattr(usage, "input_tokens", reservation["input_tokens"])),
            output_tokens=int(getattr(usage, "output_tokens", reservation["output_tokens"])),
            reason=settlement_reason,
        )
    if status != "completed":
        detail = f" ({incomplete_reason})" if incomplete_reason else ""
        raise RuntimeError(f"OpenAI response ended with status: {status}{detail}")
    return response, ledger
