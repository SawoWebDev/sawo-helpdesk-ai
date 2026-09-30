from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, event, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.rag.question_normalize import normalize_question


class FAQPhrasing(Base):
    """A staff-reviewed alternate wording of a canonical FAQ's question.

    Holds no answer text: a match always serves the canonical FAQ's current
    answer, read by faq_id, so the FAQ stays the single source of truth.
    Only ever created through the staff FAQ endpoints — never automatically
    from chat or AI output (see routers/faqs.py and crud/faq_phrasing.py)."""

    __tablename__ = "faq_phrasings"

    id: Mapped[int] = mapped_column(primary_key=True)
    faq_id: Mapped[int] = mapped_column(
        ForeignKey("faq_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phrasing: Mapped[str] = mapped_column(Text, nullable=False)
    # One wording can only ever point at one FAQ: unique across the table.
    phrasing_normalized: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    has_embedding: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


@event.listens_for(FAQPhrasing, "before_insert")
@event.listens_for(FAQPhrasing, "before_update")
def _sync_phrasing_normalized(_mapper, _connection, target: FAQPhrasing) -> None:
    target.phrasing_normalized = normalize_question(target.phrasing)
