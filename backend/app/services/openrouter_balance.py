import httpx

CREDITS_URL = "https://openrouter.ai/api/v1/credits"


class OpenRouterBalanceError(Exception):
    pass


async def get_credit_balance(api_key: str) -> dict:
    """Account-wide credit balance from OpenRouter's own /credits endpoint,
    using the management key configured in Settings — a read-only account
    query, unrelated to the inference key used for chat/embedding calls."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(CREDITS_URL, headers={"Authorization": f"Bearer {api_key}"})
        except httpx.HTTPError as e:
            raise OpenRouterBalanceError(f"Could not reach OpenRouter: {e}") from e

    if resp.status_code == 401:
        raise OpenRouterBalanceError("OpenRouter rejected the management API key (401 Unauthorized).")
    if resp.status_code != 200:
        raise OpenRouterBalanceError(f"OpenRouter returned {resp.status_code}.")

    data = resp.json().get("data", {})
    total_credits = float(data.get("total_credits", 0.0))
    total_usage = float(data.get("total_usage", 0.0))
    return {
        "total_credits": total_credits,
        "total_usage": total_usage,
        "balance": total_credits - total_usage,
    }
