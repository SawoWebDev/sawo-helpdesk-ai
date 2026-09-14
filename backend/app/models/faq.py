from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FAQEntry(Base):
    __tablename__ = "faq_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
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
