from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class HarvestSource(Base):
    __tablename__ = "harvest_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("harvest_jobs.id", ondelete="SET NULL"), nullable=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    origin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    crawl_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Pending -> Processing -> Indexed (or Failed). "Indexed" means chunked +
    # embedded into vault_entries; FAQ generation is a separate, optional step
    # tracked by faq_generation_status below so re-running it doesn't require
    # re-parsing/re-chunking the source.
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_char_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    auto_generate_faqs: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    faq_generation_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    generated_faq_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped["HarvestJob"] = relationship("HarvestJob")  # noqa: F821
    category: Mapped["Category"] = relationship("Category")  # noqa: F821
