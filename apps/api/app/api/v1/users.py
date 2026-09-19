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
    for field, value in changes.items():
        setattr(ctx.user, field, value)
    await db.commit()
    return ok(user_out(ctx.user))
