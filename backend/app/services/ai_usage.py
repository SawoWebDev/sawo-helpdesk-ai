"""Records OpenRouter token usage per request, independent of the caller's
own DB session — OpenRouterEngine is constructed fresh from plain settings
values in many call sites (RAG pipeline, FAQ generation, Library ingestion,
reindexing) with no session threaded into generate()/embed(), so usage
logging opens its own short-lived session rather than changing every one of
those call sites' signatures."""

import logging

from app.db.session import AsyncSessionLocal
from app.models.ai_usage_log import AIUsageLog

logger = logging.getLogger(__name__)


async def record_usage(model: str, request_type: str, usage: dict | None) -> None:
    if not usage:
        return
    try:
        async with AsyncSessionLocal() as db:
            db.add(
                AIUsageLog(
                    model=model,
                    is_free=model.endswith(":free"),
                    request_type=request_type,
                    prompt_tokens=int(usage.get("prompt_tokens") or 0),
                    completion_tokens=int(usage.get("completion_tokens") or 0),
                    total_tokens=int(usage.get("total_tokens") or 0),
                    cost_usd=float(usage.get("cost") or 0.0),
                )
            )
            await db.commit()
    except Exception:
        # Usage tracking is a monitoring side-effect, never allowed to break
        # the actual chat/embedding request it's observing.
        logger.exception("Failed to record AI usage log for model %s", model)
