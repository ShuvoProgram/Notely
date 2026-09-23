from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response

from app.api.deps import CurrentAuth, DbDep
from app.api.v1.auth import user_out
from app.core.exceptions import NotFound
from app.core.responses import Envelope, ok
from app.schemas.auth import UpdateProfileRequest, UserOut
from app.services.avatar_service import MAX_UPLOAD_BYTES, AvatarService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=Envelope[UserOut])
async def me(ctx: CurrentAuth) -> dict[str, Any]:
    return ok(user_out(ctx.user))


@router.patch("/me", response_model=Envelope[UserOut])
async def update_me(payload: UpdateProfileRequest, ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    notifications = changes.pop("notifications", None)
    sound = changes.pop("sound", None)
    appearance = changes.pop("appearance", None)
    for field, value in changes.items():
        setattr(ctx.user, field, value)
    if notifications is not None or sound is not None or appearance is not None:
        prefs = dict(ctx.user.preferences or {})
        if notifications is not None:
            prefs["notifications"] = {**dict(prefs.get("notifications") or {}), **notifications}
        if sound is not None:
            prefs["sound"] = sound
        if appearance is not None:
            prefs["appearance"] = appearance
        ctx.user.preferences = prefs
    await db.commit()
    return ok(user_out(ctx.user))


# --- profile picture ------------------------------------------------------------------------------


@router.put("/me/avatar", response_model=Envelope[UserOut])
async def upload_avatar(
    ctx: CurrentAuth, db: DbDep, file: Annotated[UploadFile, File()]
) -> dict[str, Any]:
    """Replace the profile picture. The image is validated and re-encoded server-side."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    user = await AvatarService(db).set(ctx.user, data)
    return ok(user_out(user))


@router.delete("/me/avatar", response_model=Envelope[UserOut])
async def remove_avatar(ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    """Back to initials. Also clears a picture that came from a sign-in provider."""
    return ok(user_out(await AvatarService(db).remove(ctx.user)))


@router.get("/{user_id}/avatar")
async def get_avatar(user_id: uuid.UUID, ctx: CurrentAuth, db: DbDep) -> Response:
    row = await AvatarService(db).get_for(ctx.user, user_id)
    if row is None:
        raise NotFound("No profile picture.")
    # The URL carries a content hash (?v=), so the response can be cached for a long time.
    return Response(
        content=row.content,
        media_type=row.content_type,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )
