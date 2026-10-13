from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatReport(Base):
    """A staff-submitted "report a problem" for one assistant reply. Snapshots
    the question/answer/sources shown at report time (rather than joining back
    to ChatLog for them), so the report still reads correctly even if the
    source chat log is later edited or bulk-deleted from Chat Logs."""

    __tablename__ = "chat_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_log_id: Mapped[int] = mapped_column(
        ForeignKey("chat_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    reference_urls: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", server_default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Username snapshot (not a users.id FK) for the same reason question_text/
    # answer_text are snapshots rather than joins — stays readable even if
    # that staff account is later deleted. Cleared on reopen.
    resolved_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
