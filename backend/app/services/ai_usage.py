"""Records OpenRouter token usage per request, independent of the caller's
own DB session — OpenRouterEngine is constructed fresh from plain settings
values in many call sites (RAG pipeline, FAQ generation, Library ingestion,
reindexing) with no session threaded into generate()/embed(), so usage
logging opens its own short-lived session rather than changing every one of
those call sites' signatures."""

import logging
from contextlib import contextmanager
from contextvars import ContextVar

from app.db.session import AsyncSessionLocal
from app.models.ai_usage_log import AIUsageLog

logger = logging.getLogger(__name__)

# Same "don't change every call site" reasoning as the module docstring above,
# applied to linking a usage row back to the chat session that caused it: the
# RAG pipeline sets this once per incoming question (see
# rag.pipeline.answer_question) rather than threading session_id through
# AIEngine.generate()/embed() and every helper that calls them. A contextvar
# survives into `asyncio.create_task(record_usage(...))` (task creation
# captures the current context) despite that being a new Task, so this still
# works with the fire-and-forget usage recording below.
_current_session_id: ContextVar[str | None] = ContextVar("current_session_id", default=None)


@contextmanager
def session_context(session_id: str | None):
    token = _current_session_id.set(session_id)
    try:
        yield
    finally:
        _current_session_id.reset(token)


async def record_usage(
    model: str,
    request_type: str,
    usage: dict | None,
    provider: str | None = None,
    finish_reason: str | None = None,
    latency_ms: int | None = None,
) -> None:
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
                    session_id=_current_session_id.get(),
                    provider=provider,
                    finish_reason=finish_reason,
                    latency_ms=latency_ms,
                )
            )
            await db.commit()
    except Exception:
        # Usage tracking is a monitoring side-effect, never allowed to break
        # the actual chat/embedding request it's observing.
        logger.exception("Failed to record AI usage log for model %s", model)
