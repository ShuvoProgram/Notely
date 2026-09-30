"""Change history: what each AI run / automation run changed, and reverting it.

A revert needs `confirm: true` (the client shows a preview first), runs at most once per batch,
and reports every change it could not undo instead of claiming success.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import CurrentAuth, DbDep, SettingsDep
from app.core.exceptions import ValidationFailed
from app.core.rate_limit import rate_limit
from app.core.responses import Envelope, ok
from app.services.batch_revert import BatchRevertService

router = APIRouter(prefix="/history", tags=["history"])
revert_limit = rate_limit("revert", 20)

BatchKind = Literal["ai_run", "automation_run"]


class RevertRequest(BaseModel):
    confirm: bool
    retry: bool = False


@router.get("", response_model=Envelope[list[dict[str, Any]]])
async def list_history(
    ctx: CurrentAuth,
    db: DbDep,
    settings: SettingsDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> dict[str, Any]:
    return ok(await BatchRevertService(db, settings).list_batches(ctx.user, limit=limit))


@router.get("/{kind}/{batch_id}", response_model=Envelope[dict[str, Any]])
async def preview(
    kind: BatchKind, batch_id: uuid.UUID, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    """The batch's changes plus a dry run: what a revert would undo, leave, or can't undo."""
    return ok(await BatchRevertService(db, settings).preview(ctx.user, kind, batch_id))


@router.post(
    "/{kind}/{batch_id}/revert",
    response_model=Envelope[dict[str, Any]],
    dependencies=[Depends(revert_limit)],
)
async def revert(
    kind: BatchKind,
    batch_id: uuid.UUID,
    payload: RevertRequest,
    ctx: CurrentAuth,
    db: DbDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    if not payload.confirm:
        raise ValidationFailed("Confirm the revert after reviewing what it will change.")
    return ok(
        await BatchRevertService(db, settings).revert(
            ctx.user, kind, batch_id, retry=payload.retry
        )
    )
