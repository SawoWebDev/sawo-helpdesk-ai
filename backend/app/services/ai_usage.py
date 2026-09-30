"""Records OpenRouter token usage per request. Every OpenRouterEngine is
constructed via app.ai.factory.get_active_engine()/get_embedding_engine(),
which already has the caller's AsyncSession (bound to whichever database that
caller is using — the real app database, or a temporary one in tests). Usage
logging opens its own short-lived session rather than reusing that session
object directly (it runs fire-and-forget via asyncio.create_task and may
outlive the caller's session), but binds that short-lived session to the same
underlying engine/database, so a usage row always lands in the same database
as the operation that generated it."""

import logging
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

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


# Same contextvar approach as session_id above, but identifies WHICH process
# made the call (crawl/ingest, FAQ dedup check, reindex, one of the chat
# pipeline's several sub-calls, ...) rather than which conversation it
# belongs to. Set tightly around each individual generate()/embed() call site
# rather than around a whole enclosing function, so a shared helper like
# _is_grounded self-identifies correctly no matter which feature called it.
_current_feature: ContextVar[str | None] = ContextVar("current_feature", default=None)


@contextmanager
def feature_context(feature: str):
    token = _current_feature.set(feature)
    try:
        yield
    finally:
        _current_feature.reset(token)


# Feature taxonomy — one entry per distinct AI call site. Values are stored
# verbatim in ai_usage_logs.feature and read back by crud.analytics for the
# Analytics "AI Usage by Process" breakdown.
FEATURE_CHAT_QUERY_EMBEDDING = "chat_query_embedding"
FEATURE_RELEVANCE_CHECK = "relevance_check"
FEATURE_CHAT_ANSWER_GENERATION = "chat_answer_generation"
FEATURE_GROUNDING_CHECK = "grounding_check"
FEATURE_CHAT_OFF_TOPIC_REPLY = "chat_off_topic_reply"
FEATURE_LIBRARY_INGEST = "library_ingest"
FEATURE_LIBRARY_SEARCH = "library_search"
FEATURE_LIBRARY_SEARCH_ANSWER = "library_search_answer"
FEATURE_VAULT_SEARCH = "vault_search"
FEATURE_FAQ_DEDUP = "faq_dedup"
FEATURE_FAQ_REINDEX = "faq_reindex"
FEATURE_VAULT_REINDEX = "vault_reindex"


async def record_usage(
    model: str,
    request_type: str,
    usage: dict | None,
    db: AsyncSession,
    provider: str | None = None,
    finish_reason: str | None = None,
    latency_ms: int | None = None,
) -> None:
    if not usage:
        return
    cost_details = usage.get("cost_details") or {}

    def _optional_float(value):
        return float(value) if value is not None else None

    try:
        # Bind a fresh, short-lived session to the SAME engine as the
        # caller's `db` (rather than reusing `db` itself, which this
        # fire-and-forget task may outlive). This is what keeps usage
        # logging inside whichever database — real or a test's temporary
        # one — the calling operation is actually using.
        session_factory = async_sessionmaker(
            bind=AsyncEngine(db.get_bind()), class_=AsyncSession, expire_on_commit=False
        )
        async with session_factory() as usage_db:
            usage_db.add(
                AIUsageLog(
                    model=model,
                    is_free=model.endswith(":free"),
                    request_type=request_type,
                    prompt_tokens=int(usage.get("prompt_tokens") or 0),
                    completion_tokens=int(usage.get("completion_tokens") or 0),
                    total_tokens=int(usage.get("total_tokens") or 0),
                    cost_usd=float(usage.get("cost") or 0.0),
                    input_cost_usd=_optional_float(cost_details.get("upstream_inference_prompt_cost")),
                    output_cost_usd=_optional_float(cost_details.get("upstream_inference_completions_cost")),
                    session_id=_current_session_id.get(),
                    feature=_current_feature.get(),
                    provider=provider,
                    finish_reason=finish_reason,
                    latency_ms=latency_ms,
                )
            )
            await usage_db.commit()
    except Exception:
        # Usage tracking is a monitoring side-effect, never allowed to break
        # the actual chat/embedding request it's observing.
        logger.exception("Failed to record AI usage log for model %s", model)
