from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import CurrentAuth, DbDep
from app.api.v1.auth import user_out
from app.core.responses import Envelope, ok
from app.schemas.auth import UpdateProfileRequest, UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=Envelope[UserOut])
async def me(ctx: CurrentAuth) -> dict[str, Any]:
    return ok(user_out(ctx.user))


@router.patch("/me", response_model=Envelope[UserOut])
async def update_me(payload: UpdateProfileRequest, ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    notifications = changes.pop("notifications", None)
    sound = changes.pop("sound", None)
    for field, value in changes.items():
        setattr(ctx.user, field, value)
    if notifications is not None or sound is not None:
        prefs = dict(ctx.user.preferences or {})
        if notifications is not None:
            prefs["notifications"] = {**dict(prefs.get("notifications") or {}), **notifications}
        if sound is not None:
            prefs["sound"] = sound
        ctx.user.preferences = prefs
    await db.commit()
    return ok(user_out(ctx.user))
