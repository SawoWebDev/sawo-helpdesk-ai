import time

import httpx

TTL_SECONDS = 60 * 60  # 1 hour

# Caches OpenRouter's raw /models list once — the model picker's catalog
# lookup (see app/services/model_catalog.py) derives from this same fetch
# rather than hitting the endpoint on every request.
_cache: dict = {"list": None, "fetched_at": 0.0}


async def _load_models_list() -> list[dict]:
    now = time.time()
    if _cache["list"] is not None and now - _cache["fetched_at"] < TTL_SECONDS:
        return _cache["list"]

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get("https://openrouter.ai/api/v1/models")
    if resp.status_code != 200:
        return _cache["list"] or []

    data = resp.json()
    _cache["list"] = data.get("data", [])
    _cache["fetched_at"] = now
    return _cache["list"]


async def get_model_catalog(model_ids: list[str]) -> list[dict | None]:
    """Raw catalog entries (id/name/description/pricing/context_length as
    OpenRouter itself returns them) for a given set of model ids."""
    models = await _load_models_list()
    by_id = {m["id"]: m for m in models}
    return [by_id.get(model_id) for model_id in model_ids]
