from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentAuth, DbDep, SettingsDep
from app.core.rate_limit import rate_limit
from app.core.responses import Envelope, ok
from app.models.note import Folder, Note, Tag
from app.schemas.notes import (
    FolderCreate,
    FolderOut,
    FolderUpdate,
    NoteCreate,
    NoteListQuery,
    NoteOut,
    NoteSummary,
    NoteUpdate,
    SearchHit,
    SearchResponse,
    SearchSource,
    TagCreate,
    TagOut,
    TagUpdate,
)
from app.services.note_service import NoteService
from app.services.rich_text import excerpt

notes_router = APIRouter(prefix="/notes", tags=["notes"])
folders_router = APIRouter(prefix="/folders", tags=["folders"])
tags_router = APIRouter(prefix="/tags", tags=["tags"])
search_router = APIRouter(prefix="/search", tags=["search"])


def get_note_service(db: DbDep) -> NoteService:
    return NoteService(db)


ServiceDep = Annotated[NoteService, Depends(get_note_service)]


def tag_out(tag: Tag, count: int = 0) -> TagOut:
    return TagOut(id=tag.id, name=tag.name, color=tag.color, note_count=count)


def folder_out(folder: Folder, count: int = 0) -> FolderOut:
    return FolderOut(
        id=folder.id,
        name=folder.name,
        parent_id=folder.parent_id,
        position=folder.position,
        note_count=count,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


def _common(note: Note) -> dict[str, Any]:
    return {
        "id": note.id,
        "title": note.title,
        "excerpt": excerpt(note.plain_text),
        "folder_id": note.folder_id,
        "tags": [tag_out(t) for t in note.tags],
        "is_favorite": note.is_favorite,
        "archived_at": note.archived_at,
        "deleted_at": note.deleted_at,
        "version": note.version,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }


def note_summary(note: Note) -> NoteSummary:
    return NoteSummary(**_common(note))


def note_out(note: Note) -> NoteOut:
    return NoteOut(
        **_common(note),
        content_json=note.content_json,
        plain_text=note.plain_text,
        summary=note.summary,
        metadata=note.metadata_,
    )


# --- notes --------------------------------------------------------------------------------------


@notes_router.get("", response_model=Envelope[list[NoteSummary]])
async def list_notes(
    ctx: CurrentAuth, service: ServiceDep, query: Annotated[NoteListQuery, Query()]
) -> dict[str, Any]:
    notes, next_cursor = await service.list_notes(ctx.user, query)
    return ok([note_summary(n) for n in notes], {"next_cursor": next_cursor})


@notes_router.post("", status_code=status.HTTP_201_CREATED, response_model=Envelope[NoteOut])
async def create_note(payload: NoteCreate, ctx: CurrentAuth, service: ServiceDep) -> dict[str, Any]:
    return ok(note_out(await service.create_note(ctx.user, payload)))


@notes_router.get("/{note_id}", response_model=Envelope[NoteOut])
async def get_note(note_id: uuid.UUID, ctx: CurrentAuth, service: ServiceDep) -> dict[str, Any]:
    return ok(note_out(await service.get_note(ctx.user, note_id)))


@notes_router.patch("/{note_id}", response_model=Envelope[NoteOut])
async def update_note(
    note_id: uuid.UUID, payload: NoteUpdate, ctx: CurrentAuth, service: ServiceDep
) -> dict[str, Any]:
    return ok(note_out(await service.update_note(ctx.user, note_id, payload)))


@notes_router.delete("/{note_id}", response_model=Envelope[NoteSummary])
async def trash_note(note_id: uuid.UUID, ctx: CurrentAuth, service: ServiceDep) -> dict[str, Any]:
    return ok(note_summary(await service.trash_note(ctx.user, note_id)))


@notes_router.post("/{note_id}/restore", response_model=Envelope[NoteSummary])
async def restore_note(note_id: uuid.UUID, ctx: CurrentAuth, service: ServiceDep) -> dict[str, Any]:
    return ok(note_summary(await service.restore_note(ctx.user, note_id)))


@notes_router.delete("/{note_id}/permanent", response_model=Envelope[dict[str, bool]])
async def purge_note(note_id: uuid.UUID, ctx: CurrentAuth, service: ServiceDep) -> dict[str, Any]:
    await service.purge_note(ctx.user, note_id)
    return ok({"deleted": True})


@notes_router.post(
    "/{note_id}/duplicate", status_code=status.HTTP_201_CREATED, response_model=Envelope[NoteOut]
)
async def duplicate_note(
    note_id: uuid.UUID, ctx: CurrentAuth, service: ServiceDep
) -> dict[str, Any]:
    return ok(note_out(await service.duplicate_note(ctx.user, note_id)))


# --- folders ------------------------------------------------------------------------------------


@folders_router.get("", response_model=Envelope[list[FolderOut]])
async def list_folders(ctx: CurrentAuth, service: ServiceDep) -> dict[str, Any]:
    return ok([folder_out(f, n) for f, n in await service.list_folders(ctx.user)])


@folders_router.post("", status_code=status.HTTP_201_CREATED, response_model=Envelope[FolderOut])
async def create_folder(
    payload: FolderCreate, ctx: CurrentAuth, service: ServiceDep
) -> dict[str, Any]:
    return ok(folder_out(await service.create_folder(ctx.user, payload)))


@folders_router.patch("/{folder_id}", response_model=Envelope[FolderOut])
async def update_folder(
    folder_id: uuid.UUID, payload: FolderUpdate, ctx: CurrentAuth, service: ServiceDep
) -> dict[str, Any]:
    return ok(folder_out(await service.update_folder(ctx.user, folder_id, payload)))


@folders_router.delete("/{folder_id}", response_model=Envelope[dict[str, bool]])
async def delete_folder(
    folder_id: uuid.UUID, ctx: CurrentAuth, service: ServiceDep
) -> dict[str, Any]:
    await service.delete_folder(ctx.user, folder_id)
    return ok({"deleted": True})


# --- tags ---------------------------------------------------------------------------------------


@tags_router.get("", response_model=Envelope[list[TagOut]])
async def list_tags(ctx: CurrentAuth, service: ServiceDep) -> dict[str, Any]:
    return ok([tag_out(t, n) for t, n in await service.list_tags(ctx.user)])


@tags_router.post("", status_code=status.HTTP_201_CREATED, response_model=Envelope[TagOut])
async def create_tag(payload: TagCreate, ctx: CurrentAuth, service: ServiceDep) -> dict[str, Any]:
    return ok(tag_out(await service.create_tag(ctx.user, payload)))


@tags_router.patch("/{tag_id}", response_model=Envelope[TagOut])
async def update_tag(
    tag_id: uuid.UUID, payload: TagUpdate, ctx: CurrentAuth, service: ServiceDep
) -> dict[str, Any]:
    return ok(tag_out(await service.update_tag(ctx.user, tag_id, payload)))


@tags_router.delete("/{tag_id}", response_model=Envelope[dict[str, bool]])
async def delete_tag(tag_id: uuid.UUID, ctx: CurrentAuth, service: ServiceDep) -> dict[str, Any]:
    await service.delete_tag(ctx.user, tag_id)
    return ok({"deleted": True})


# --- unified search -----------------------------------------------------------------------------


@search_router.get(
    "",
    response_model=Envelope[SearchResponse],
    dependencies=[Depends(rate_limit("search", lambda s: s.rate_limit_search_per_minute))],
)
async def search(
    ctx: CurrentAuth,
    db: DbDep,
    settings: SettingsDep,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> dict[str, Any]:
    """Unified search across Notely and every connected provider. Every hit names its source."""
    from app.services.search_service import UnifiedSearchService

    result = await UnifiedSearchService(db, settings).search(ctx.user, q, limit)
    return ok(
        SearchResponse(
            query=result.query,
            hits=[SearchHit(**h.__dict__) for h in result.hits],
            sources=[SearchSource(**s.__dict__) for s in result.sources],
        )
    )
