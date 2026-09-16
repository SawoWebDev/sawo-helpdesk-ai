from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatLog(Base):
    __tablename__ = "chat_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    matched_faq_ids: Mapped[list[int]] = mapped_column(JSON, default=list, server_default="[]")
    matched_vault_ids: Mapped[list[int]] = mapped_column(JSON, default=list, server_default="[]")
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    engine_used: Mapped[str] = mapped_column(String(50), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
