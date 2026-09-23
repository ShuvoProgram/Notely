from __future__ import annotations

import hashlib
import io
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailed
from app.db.base import utcnow
from app.models.avatar import UserAvatar
from app.models.user import User

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000  # refuse decompression bombs long before Pillow's own limit
SIZE = 256
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP", "GIF"}


def avatar_url(user_id: uuid.UUID, content: bytes) -> str:
    # The version suffix changes with the picture, so browsers never show a stale cached image.
    return f"/api/v1/users/{user_id}/avatar?v={hashlib.sha256(content).hexdigest()[:12]}"


def normalise(data: bytes) -> bytes:
    """Validate an uploaded picture and re-encode it as a centred square WebP.

    Re-encoding (rather than storing the upload) drops metadata such as GPS location and any
    payload smuggled after the image data. Raises ValidationFailed with a user-readable message.
    """
    if not data:
        raise ValidationFailed("Choose an image to upload.", code="AVATAR_EMPTY")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValidationFailed(
            "That image is over 5 MB. Choose a smaller one.", code="AVATAR_TOO_LARGE"
        )
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            width, height = probe.size
            probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ValidationFailed(
            "That file isn't an image we can use. Try a JPG, PNG, WebP or GIF.",
            code="AVATAR_UNREADABLE",
        ) from exc
    if fmt not in ALLOWED_FORMATS:
        raise ValidationFailed("Use a JPG, PNG, WebP or GIF image.", code="AVATAR_TYPE")
    if width * height > MAX_PIXELS:
        raise ValidationFailed("That image is too large to process.", code="AVATAR_TOO_LARGE")
    with Image.open(io.BytesIO(data)) as img:
        img.seek(0)  # first frame of an animated GIF/WebP
        frame = ImageOps.exif_transpose(img).convert("RGBA")
    square = ImageOps.fit(frame, (SIZE, SIZE), method=Image.Resampling.LANCZOS)
    out = io.BytesIO()
    square.save(out, format="WEBP", quality=86, method=6)
    return out.getvalue()


class AvatarService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def set(self, user: User, data: bytes) -> User:
        content = normalise(data)
        row = await self.db.get(UserAvatar, user.id)
        if row is None:
            row = UserAvatar(user_id=user.id, content=content, content_type="image/webp")
            self.db.add(row)
        else:
            row.content = content
            row.content_type = "image/webp"
            row.updated_at = utcnow()
        user.avatar_url = avatar_url(user.id, content)
        await self.db.commit()
        return user

    async def remove(self, user: User) -> User:
        row = await self.db.get(UserAvatar, user.id)
        if row is not None:
            await self.db.delete(row)
        user.avatar_url = None
        await self.db.commit()
        return user

    async def get_for(self, viewer: User, user_id: uuid.UUID) -> UserAvatar | None:
        # Pictures are visible inside the viewer's workspace only.
        owner = await self.db.scalar(
            select(User).where(User.id == user_id, User.tenant_id == viewer.tenant_id)
        )
        if owner is None:
            return None
        return await self.db.get(UserAvatar, user_id)
