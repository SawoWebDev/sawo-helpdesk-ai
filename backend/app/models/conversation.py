from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Conversation(Base):
    """One private, owner-scoped conversation thread. `owner_hash` is the
    SHA-256 hash of a browser-owner token stored in an httpOnly cookie — this
    app has no staff login, so this is the only identity a conversation has."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
