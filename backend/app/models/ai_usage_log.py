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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
