from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    is_free: Mapped[bool] = mapped_column(Boolean, nullable=False)
    request_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "chat" | "embedding"
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # USD cost as reported by OpenRouter's own usage.cost field on the
    # response — always 0.0 for :free models, real billed cost for paid
    # ones. Not estimated from token counts, since OpenRouter already gives
    # the authoritative number per request.
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    # The chat session this call was made for, when it was made inside the
    # RAG pipeline answering a visitor question — NULL for usage with no chat
    # session context (FAQ generation, Library ingestion, reindexing). Lets
    # the Chat Logs "consumption" view attribute cost/tokens to a conversation.
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # OpenRouter's own response fields — which upstream inference provider it
    # routed the request to (e.g. "GMICloud" for an open-weight model like
    # deepseek-v4-flash), and how generation ended ("stop", "length", etc).
    # NULL for embeddings, which have neither.
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Wall-clock time for the OpenRouter request itself (excludes retries),
    # timed client-side since OpenRouter doesn't report this in the response.
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
