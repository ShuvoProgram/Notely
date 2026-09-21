from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentAuth, DbDep, SettingsDep
from app.core.rate_limit import rate_limit
from app.core.responses import Envelope, ok
from app.models.note import Folder, Note, NoteCollaborator, Tag
from app.models.user import User
from app.schemas.notes import (
    BulkIds,
    ChecklistProgress,
    CollaboratorInvite,
    CollaboratorOut,
    CollaboratorUpdate,
    DeliveryOut,
    FolderCreate,
    FolderOut,
    FolderUpdate,
    InvitationOut,
    InviteResult,
    NoteCreate,
    NoteListQuery,
    NoteOut,
    NoteSummary,
    NoteUpdate,
    NoteVersionDetail,
    NoteVersionOut,
    SearchHit,
    SearchResponse,
    SearchSource,
    TagCreate,
    TagOut,
    TagUpdate,
)
from app.services.note_service import NoteService
from app.services.rich_text import checklist_progress, excerpt

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


def _common(note: Note, user: User) -> dict[str, Any]:
    done, total = checklist_progress(note.content_json)
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
        "color": note.color,
        "reminder_at": note.reminder_at,
        "checklist": ChecklistProgress(done=done, total=total) if total else None,
        "shared": bool(note.collaborators),
        "access": NoteService.access_of(user, note),
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }


def note_summary(note: Note, user: User) -> NoteSummary:
    return NoteSummary(**_common(note, user))


def collaborator_out(c: NoteCollaborator) -> CollaboratorOut:
    return CollaboratorOut(
        id=c.id,
        email=c.email,
        role=c.role,
        user_id=c.user_id,
        status=NoteService.invitation_status(c),
        invited_at=c.invited_at,
        accepted_at=c.accepted_at,
        invite_expires_at=c.invite_expires_at,
        created_at=c.created_at,
    )


def note_out(note: Note, user: User) -> NoteOut:
    return NoteOut(
        **_common(note, user),
        content_json=note.content_json,
        plain_text=note.plain_text,
        summary=note.summary,
        metadata=note.metadata_,
        collaborators=[collaborator_out(c) for c in note.collaborators],
    )


# --- notes --------------------------------------------------------------------------------------


@notes_router.get("", response_model=Envelope[list[NoteSummary]])
async def list_notes(
    ctx: CurrentAuth, service: ServiceDep, query: Annotated[NoteListQuery, Query()]
) -> dict[str, Any]:
    notes, next_cursor = await service.list_notes(ctx.user, query)
    return ok([note_summary(n, ctx.user) for n in notes], {"next_cursor": next_cursor})


@notes_router.post("", status_code=status.HTTP_201_CREATED, response_model=Envelope[NoteOut])
async def create_note(payload: NoteCreate, ctx: CurrentAuth, service: ServiceDep) -> dict[str, Any]:
    return ok(note_out(await service.create_note(ctx.user, payload), ctx.user))


@notes_router.get("/{note_id}", response_model=Envelope[NoteOut])
async def get_note(note_id: uuid.UUID, ctx: CurrentAuth, service: ServiceDep) -> dict[str, Any]:
    return ok(note_out(await service.get_note(ctx.user, note_id), ctx.user))


@notes_router.patch("/{note_id}", response_model=Envelope[NoteOut])
async def update_note(
    note_id: uuid.UUID, payload: NoteUpdate, ctx: CurrentAuth, service: ServiceDep
) -> dict[str, Any]:
    return ok(note_out(await service.update_note(ctx.user, note_id, payload), ctx.user))


@notes_router.delete("/{note_id}", response_model=Envelope[NoteSummary])
async def trash_note(note_id: uuid.UUID, ctx: CurrentAuth, service: ServiceDep) -> dict[str, Any]:
    return ok(note_summary(await service.trash_note(ctx.user, note_id), ctx.user))


@notes_router.post("/bulk/trash", response_model=Envelope[dict[str, int]])
async def trash_notes(payload: BulkIds, ctx: CurrentAuth, service: ServiceDep) -> dict[str, Any]:
    """Bulk "move to trash" from the list's selection mode. Reversible per note via restore."""
    return ok({"moved": await service.trash_many(ctx.user, payload.ids)})


@notes_router.post("/{note_id}/restore", response_model=Envelope[NoteSummary])
async def restore_note(note_id: uuid.UUID, ctx: CurrentAuth, service: ServiceDep) -> dict[str, Any]:
    return ok(note_summary(await service.restore_note(ctx.user, note_id), ctx.user))


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
    return ok(note_out(await service.duplicate_note(ctx.user, note_id), ctx.user))


# --- version history ---------------------------------------------------------------------------


@notes_router.get("/{note_id}/versions", response_model=Envelope[list[NoteVersionOut]])
async def list_versions(
    note_id: uuid.UUID, ctx: CurrentAuth, service: ServiceDep
) -> dict[str, Any]:
    rows = await service.list_versions(ctx.user, note_id)
    return ok([NoteVersionOut.model_validate(v) for v in rows])


@notes_router.get("/{note_id}/versions/{version_id}", response_model=Envelope[NoteVersionDetail])
async def get_version(
    note_id: uuid.UUID, version_id: uuid.UUID, ctx: CurrentAuth, service: ServiceDep
) -> dict[str, Any]:
    return ok(
        NoteVersionDetail.model_validate(await service.get_version(ctx.user, note_id, version_id))
    )


@notes_router.post("/{note_id}/versions/{version_id}/restore", response_model=Envelope[NoteOut])
async def restore_version(
    note_id: uuid.UUID, version_id: uuid.UUID, ctx: CurrentAuth, service: ServiceDep
) -> dict[str, Any]:
    return ok(note_out(await service.restore_version(ctx.user, note_id, version_id), ctx.user))


# --- collaboration -----------------------------------------------------------------------------


@notes_router.post(
    "/{note_id}/collaborators",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[InviteResult],
)
async def invite_collaborator(
    note_id: uuid.UUID, payload: CollaboratorInvite, ctx: CurrentAuth, service: ServiceDep
) -> dict[str, Any]:
    row, delivery = await service.invite(ctx.user, note_id, payload)
    return ok(
        InviteResult(
            collaborator=collaborator_out(row),
            delivery=DeliveryOut(sent=delivery.sent, error=delivery.error),
        )
    )


invitations_router = APIRouter(prefix="/invitations", tags=["notes"])


@invitations_router.get("/{token}", response_model=Envelope[InvitationOut])
async def get_invitation(token: str, service: ServiceDep) -> dict[str, Any]:
    """Public: what the link is for, so the accept page can explain before sign-in."""
    row, note, inviter = await service.get_invitation(token)
    return ok(
        InvitationOut(
            note_id=note.id,
            note_title=note.title or "Untitled",
            inviter_name=inviter.display_name,
            email=row.email,
            role=row.role,
            status=NoteService.invitation_status(row),
            expires_at=row.invite_expires_at,
        )
    )


@invitations_router.post("/{token}/accept", response_model=Envelope[NoteOut])
async def accept_invitation(token: str, ctx: CurrentAuth, service: ServiceDep) -> dict[str, Any]:
    note = await service.accept_invitation(ctx.user, token)
    return ok(note_out(note, ctx.user))


@notes_router.patch(
    "/{note_id}/collaborators/{collaborator_id}", response_model=Envelope[CollaboratorOut]
)
async def update_collaborator(
    note_id: uuid.UUID,
    collaborator_id: uuid.UUID,
    payload: CollaboratorUpdate,
    ctx: CurrentAuth,
    service: ServiceDep,
) -> dict[str, Any]:
    row = await service.update_collaborator(ctx.user, note_id, collaborator_id, payload.role)
    return ok(collaborator_out(row))


@notes_router.delete(
    "/{note_id}/collaborators/{collaborator_id}", response_model=Envelope[dict[str, bool]]
)
async def remove_collaborator(
    note_id: uuid.UUID, collaborator_id: uuid.UUID, ctx: CurrentAuth, service: ServiceDep
) -> dict[str, Any]:
    await service.remove_collaborator(ctx.user, note_id, collaborator_id)
    return ok({"removed": True})


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
