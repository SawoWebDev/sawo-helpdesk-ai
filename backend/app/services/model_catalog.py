import re

from app.services.openrouter_pricing import get_model_catalog

# A deliberately small, curated shortlist for the Settings page's model
# picker — not OpenRouter's full multi-hundred-model catalog, which would
# turn "pick a chat model" into an unusable wall of options. Order here is
# the display order before the price sort below; RECOMMENDED_MODEL_ID gets
# the picker's highlighted "Recommended" treatment.
#
# This bot is a text-only RAG support widget — it never sends or receives
# images — so flagship multimodal/reasoning tiers are deliberately left out:
# their extra cost buys capability this use case never exercises. Every
# model kept here is a well-established "everyday conversation" pick from
# its own provider, priced for high-volume chat rather than premium use.
CURATED_MODEL_IDS = [
    "deepseek/deepseek-v4-flash",
    "openai/gpt-4o-mini",
    "anthropic/claude-3-haiku",
    "anthropic/claude-3.5-sonnet",
    "google/gemini-2.0-flash-001",
]
RECOMMENDED_MODEL_ID = "deepseek/deepseek-v4-flash"

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _first_sentence(text: str | None) -> str | None:
    """OpenRouter model descriptions are often a full paragraph — the picker
    only has room for one line, so this keeps just the first sentence."""
    if not text:
        return None
    cut = _SENTENCE_SPLIT.split(text)[0]
    return cut if len(cut) <= 160 else cut[:157] + "…"


def _price_tier(price_per_m_input: float | None, price_per_m_output: float | None) -> str | None:
    """A simple, at-a-glance price tier — separate from the single
    "Recommended" pick, which is a specific editorial choice, not just "the
    cheapest one". Blended = average of input/output per-million price,
    since a model can be cheap on one side and expensive on the other."""
    if price_per_m_input is None or price_per_m_output is None:
        return None
    blended = (price_per_m_input + price_per_m_output) / 2
    if blended <= 0.5:
        return "cheap"
    if blended <= 5:
        return "balanced"
    return "premium"


async def get_curated_models() -> list[dict]:
    entries = await get_model_catalog(CURATED_MODEL_IDS)

    models = []
    for model_id, m in zip(CURATED_MODEL_IDS, entries):
        if m is None:
            # A curated id OpenRouter doesn't currently list can't show real
            # pricing/reliability info anyway — dropped rather than shown as
            # a dead entry the admin can't actually evaluate.
            continue
        pricing = m.get("pricing") or {}
        prompt_price = float(pricing.get("prompt") or 0)
        completion_price = float(pricing.get("completion") or 0)
        # Per-million-token price — OpenRouter's own pricing is per single
        # token, which is an unreadably tiny decimal (e.g. 0.00000015).
        price_per_m_input = round(prompt_price * 1e6, 3)
        price_per_m_output = round(completion_price * 1e6, 3)
        models.append(
            {
                "id": model_id,
                "provider": model_id.split("/")[0],
                "name": m.get("name") or model_id,
                "description": _first_sentence(m.get("description")),
                "context_length": m.get("context_length"),
                "price_per_m_input": price_per_m_input,
                "price_per_m_output": price_per_m_output,
                "tier": _price_tier(price_per_m_input, price_per_m_output),
                "recommended": model_id == RECOMMENDED_MODEL_ID,
            }
        )

    # Cheapest first (blended price ascending); a model missing pricing
    # altogether sorts last rather than crashing the comparison.
    def _blend(entry: dict) -> float:
        if entry["price_per_m_input"] is None or entry["price_per_m_output"] is None:
            return float("inf")
        return (entry["price_per_m_input"] + entry["price_per_m_output"]) / 2

    models.sort(key=_blend)
    return models
