from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, event, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.rag.question_normalize import normalize_question


class FAQEntry(Base):
    __tablename__ = "faq_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    # normalize_question(question), maintained automatically by the hook at the
    # bottom of this file — the indexed key for exact-repeat lookups
    # (rag/saved_answers.py, crud/faq.find_duplicate_faq).
    question_normalized: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    image_urls: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    reference_urls: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    has_embedding: Mapped[bool] = mapped_column(default=False, server_default="0")
    source: Mapped[str] = mapped_column(String(20), default="manual", server_default="manual")
    source_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="published", server_default="published")
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("harvest_sources.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    category: Mapped["Category"] = relationship("Category")  # noqa: F821


@event.listens_for(FAQEntry, "before_insert")
@event.listens_for(FAQEntry, "before_update")
def _sync_question_normalized(_mapper, _connection, target: FAQEntry) -> None:
    # Every ORM write path (manual create, edit, import, save-from-chat,
    # auto-promotion) goes through here, so the lookup key can't drift from
    # the question text.
    target.question_normalized = normalize_question(target.question)
