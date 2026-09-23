from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, LargeBinary, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TZDateTime, utcnow


class UserAvatar(Base):
    """A user's uploaded profile picture, already normalised (square WebP, ≤256px, no metadata).

    Kept apart from `users` so reading a user never loads image bytes. One row per user.
    """

    __tablename__ = "user_avatars"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False, default=utcnow)
