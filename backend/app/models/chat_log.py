from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, func
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
    rating: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Only meaningful (and only set by the client) when rating == "down";
    # cleared whenever the rating changes away from "down".
    feedback_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Private per-owner conversation thread this message belongs to (see
    # Conversation). Nullable because the chatbot has no login — a message is
    # only attached once it's part of a conversation the staff member can
    # later revisit, and every row logged before this feature existed stays
    # NULL rather than being guessed into an owner's history.
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
