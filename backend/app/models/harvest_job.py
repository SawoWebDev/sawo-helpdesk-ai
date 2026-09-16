from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HarvestJob(Base):
    __tablename__ = "harvest_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Admin-assigned override for the batch's display name in the Library
    # Source list (see list_sources_grouped) — None falls back to the
    # auto-derived shared-hostname/page-count label. Only the batch (parent)
    # row is nameable this way; individual pages under it keep showing their
    # real crawled URL.
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", server_default="queued")
    config: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    total_items: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_items: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    succeeded_items: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed_items: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
