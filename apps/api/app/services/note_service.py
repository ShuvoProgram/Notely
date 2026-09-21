"""Notes, folders and tags. Authorization is enforced here: every lookup is by (id, user)."""

from __future__ import annotations

import copy
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import APIError, Conflict, NotFound, ValidationFailed
from app.db.base import utcnow
from app.models.note import CollaboratorRole, Folder, Note, NoteCollaborator, NoteVersion, Tag
from app.models.notification import NotificationKind
from app.models.user import User
from app.repositories.note_repository import (
    FolderRepository,
    NoteRepository,
    SearchRow,
    TagRepository,
)
from app.schemas.notes import (
    CollaboratorInvite,
    FolderCreate,
    FolderUpdate,
    NoteCreate,
    NoteListQuery,
    NoteUpdate,
    TagCreate,
    TagUpdate,
)
from app.services.notification_service import NotificationService
from app.services.rich_text import EMPTY_DOC, to_plain_text

# A new version snapshot is taken when the previous one is older than this (or the change is a
# restore). Keystroke-level autosaves therefore collapse into one version per writing session.
VERSION_INTERVAL = timedelta(minutes=5)
VERSIONS_KEPT = 50

TRASH_RETENTION = timedelta(days=30)


class NoteVersionConflict(APIError):
    status_code = 409
    code = "NOTE_VERSION_CONFLICT"
    message = "This note was changed elsewhere. Review the latest version before saving."


class NoteService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.notes = NoteRepository(db)
        self.folders = FolderRepository(db)
        self.tags = TagRepository(db)

    # --- folders -----------------------------------------------------------------------------

    async def list_folders(self, user: User) -> list[tuple[Folder, int]]:
        return await self.folders.list_for_user(user.id)

    async def create_folder(self, user: User, payload: FolderCreate) -> Folder:
        if (
            payload.parent_id is not None
            and await self.folders.get(payload.parent_id, user.id) is None
        ):
            raise NotFound("Parent folder not found.")
        if await self.folders.name_exists(user.id, payload.parent_id, payload.name):
            raise Conflict("A folder with this name already exists here.", code="FOLDER_NAME_TAKEN")
        folder = await self.folders.create(user, payload.name, payload.parent_id)
        await self.db.commit()
        return folder

    async def update_folder(
        self, user: User, folder_id: uuid.UUID, payload: FolderUpdate
    ) -> Folder:
        folder = await self.folders.get(folder_id, user.id)
        if folder is None:
            raise NotFound("Folder not found.")
        changes = payload.model_dump(exclude_unset=True)
        new_parent = changes.get("parent_id", folder.parent_id)
        if "parent_id" in changes and new_parent is not None:
            if new_parent == folder.id:
                raise ValidationFailed("A folder cannot be its own parent.")
            if await self.folders.get(new_parent, user.id) is None:
                raise NotFound("Parent folder not found.")
            if await self._is_descendant(user, candidate=new_parent, of=folder.id):
                raise ValidationFailed("Cannot move a folder inside one of its own subfolders.")
        new_name = changes.get("name", folder.name)
        if ("name" in changes or "parent_id" in changes) and await self.folders.name_exists(
            user.id, new_parent, new_name, exclude=folder.id
        ):
            raise Conflict("A folder with this name already exists here.", code="FOLDER_NAME_TAKEN")
        for key, value in changes.items():
            setattr(folder, key, value)
        await self.db.commit()
        return folder

    async def _is_descendant(self, user: User, *, candidate: uuid.UUID, of: uuid.UUID) -> bool:
        seen: set[uuid.UUID] = set()
        current: uuid.UUID | None = candidate
        while current is not None and current not in seen:
            seen.add(current)
            if current == of:
                return True
            parent = await self.folders.get(current, user.id)
            current = parent.parent_id if parent else None
        return False

    async def delete_folder(self, user: User, folder_id: uuid.UUID) -> None:
        folder = await self.folders.get(folder_id, user.id)
        if folder is None:
            raise NotFound("Folder not found.")
        # Notes keep existing (folder_id → NULL via FK); subfolders cascade.
        await self.folders.delete(folder)
        await self.db.commit()

    # --- tags --------------------------------------------------------------------------------

    async def list_tags(self, user: User) -> list[tuple[Tag, int]]:
        return await self.tags.list_for_user(user.id)

    async def create_tag(self, user: User, payload: TagCreate) -> Tag:
        existing = await self.tags.get_by_name(user.id, payload.name)
        if existing is not None:
            raise Conflict("A tag with this name already exists.", code="TAG_NAME_TAKEN")
        tag = await self.tags.create(user, payload.name, payload.color)
        await self.db.commit()
        return tag

    async def update_tag(self, user: User, tag_id: uuid.UUID, payload: TagUpdate) -> Tag:
        tag = await self.tags.get(tag_id, user.id)
        if tag is None:
            raise NotFound("Tag not found.")
        changes = payload.model_dump(exclude_unset=True)
        if "name" in changes and changes["name"] is not None:
            other = await self.tags.get_by_name(user.id, changes["name"])
            if other is not None and other.id != tag.id:
                raise Conflict("A tag with this name already exists.", code="TAG_NAME_TAKEN")
        for key, value in changes.items():
            if value is not None or key == "color":
                setattr(tag, key, value)
        await self.db.commit()
        return tag

    async def delete_tag(self, user: User, tag_id: uuid.UUID) -> None:
        tag = await self.tags.get(tag_id, user.id)
        if tag is None:
            raise NotFound("Tag not found.")
        await self.tags.delete(tag)
        await self.db.commit()

    # --- notes -------------------------------------------------------------------------------

    async def list_notes(self, user: User, query: NoteListQuery) -> tuple[list[Note], str | None]:
        return await self.notes.list_notes(
            user.id,
            view=query.view,
            folder_id=query.folder_id,
            tag_id=query.tag_id,
            q=query.q,
            cursor=query.cursor,
            limit=query.limit,
        )

    async def get_note(self, user: User, note_id: uuid.UUID) -> Note:
        """The user's own note, or one shared with them (any role)."""
        note = await self.notes.get(note_id, user.id)
        if note is None:
            note = await self.notes.get_shared(note_id, user.id)
        if note is None:
            raise NotFound("Note not found.")
        return note

    @staticmethod
    def access_of(user: User, note: Note) -> str:
        if note.user_id == user.id:
            return "owner"
        for c in note.collaborators:
            if c.user_id == user.id:
                return c.role.value
        return "viewer"

    async def get_editable(self, user: User, note_id: uuid.UUID) -> Note:
        note = await self.get_note(user, note_id)
        if self.access_of(user, note) == "viewer":
            raise Conflict("You can view this note but not change it.", code="NOTE_READ_ONLY")
        return note

    async def create_note(self, user: User, payload: NoteCreate) -> Note:
        if (
            payload.folder_id is not None
            and await self.folders.get(payload.folder_id, user.id) is None
        ):
            raise NotFound("Folder not found.")
        doc = payload.content_json or copy.deepcopy(EMPTY_DOC)
        note = await self.notes.create(
            user,
            title=payload.title.strip(),
            content_json=doc,
            plain_text=to_plain_text(doc),
            folder_id=payload.folder_id,
        )
        if payload.tag_ids:
            await self.notes.set_tags(note, await self._resolve_tags(user, payload.tag_ids))
        await self.db.commit()
        await self.db.refresh(note)
        return note

    async def update_note(self, user: User, note_id: uuid.UUID, payload: NoteUpdate) -> Note:
        note = await self.get_editable(user, note_id)
        if note.deleted_at is not None:
            raise Conflict("This note is in the trash. Restore it to edit.", code="NOTE_IN_TRASH")
        if payload.expected_version is not None and payload.expected_version != note.version:
            raise NoteVersionConflict(details={"current_version": note.version})

        changes = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
        # Only a *real* change to title or body counts as an edit: a client re-sending what the
        # server already has (e.g. an editor normalising on mount) must not bump version /
        # updated_at, or merely opening a note would move it to the top of the list.
        content_changed = False
        before_title, before_body = note.title, note.content_json

        if "title" in changes and changes["title"] is not None:
            new_title = changes["title"].strip()
            if new_title != note.title:
                note.title = new_title
                content_changed = True
        if "content_json" in changes and changes["content_json"] is not None:
            if changes["content_json"] != note.content_json:
                note.content_json = changes["content_json"]
                note.plain_text = to_plain_text(note.content_json)
                content_changed = True
        if "color" in changes and changes["color"] is not None:
            note.color = changes["color"]
        if changes.get("clear_reminder"):
            note.reminder_at = None
        elif "reminder_at" in changes and changes["reminder_at"] is not None:
            note.reminder_at = changes["reminder_at"]
        if changes.get("clear_folder"):
            note.folder_id = None
        elif "folder_id" in changes and changes["folder_id"] is not None:
            if await self.folders.get(changes["folder_id"], user.id) is None:
                raise NotFound("Folder not found.")
            note.folder_id = changes["folder_id"]
        if "tag_ids" in changes and changes["tag_ids"] is not None:
            await self.notes.set_tags(note, await self._resolve_tags(user, changes["tag_ids"]))
        if "is_favorite" in changes and changes["is_favorite"] is not None:
            note.is_favorite = changes["is_favorite"]
        if "archived" in changes and changes["archived"] is not None:
            note.archived_at = utcnow() if changes["archived"] else None

        if content_changed:
            await self._snapshot_if_due(user, note, before_title, before_body)
            await self.notes.mark_updated(note)
        await self.db.commit()
        await self.db.refresh(note)
        return note

    # --- version history ---------------------------------------------------------------------

    async def _snapshot_if_due(
        self, user: User, note: Note, title: str, body: dict[str, Any], *, reason: str = "edit"
    ) -> None:
        """Record the *previous* state as a version unless one was taken very recently."""
        latest = await self.db.scalar(
            select(NoteVersion)
            .where(NoteVersion.note_id == note.id)
            .order_by(NoteVersion.created_at.desc())
            .limit(1)
        )
        if (
            reason == "edit"
            and latest is not None
            and utcnow() - latest.created_at < VERSION_INTERVAL
        ):
            return
        self.db.add(
            NoteVersion(
                note_id=note.id,
                user_id=user.id,
                note_version=note.version,
                title=title,
                content_json=copy.deepcopy(body),
                plain_text=to_plain_text(body),
                reason=reason,
            )
        )
        await self.db.flush()
        stale = list(
            await self.db.scalars(
                select(NoteVersion)
                .where(NoteVersion.note_id == note.id)
                .order_by(NoteVersion.created_at.desc())
                .offset(VERSIONS_KEPT)
            )
        )
        for row in stale:
            await self.db.delete(row)

    async def list_versions(self, user: User, note_id: uuid.UUID) -> list[NoteVersion]:
        note = await self.get_note(user, note_id)
        return list(
            await self.db.scalars(
                select(NoteVersion)
                .where(NoteVersion.note_id == note.id)
                .order_by(NoteVersion.created_at.desc())
            )
        )

    async def get_version(
        self, user: User, note_id: uuid.UUID, version_id: uuid.UUID
    ) -> NoteVersion:
        note = await self.get_note(user, note_id)
        row = await self.db.scalar(
            select(NoteVersion).where(NoteVersion.id == version_id, NoteVersion.note_id == note.id)
        )
        if row is None:
            raise NotFound("Version not found.")
        return row

    async def restore_version(self, user: User, note_id: uuid.UUID, version_id: uuid.UUID) -> Note:
        """Put an older version back as the current body. The current state is snapshotted
        first, so a restore is itself reversible."""
        note = await self.get_editable(user, note_id)
        row = await self.get_version(user, note_id, version_id)
        await self._snapshot_if_due(
            user, note, note.title, note.content_json, reason="before_restore"
        )
        note.title = row.title
        note.content_json = copy.deepcopy(row.content_json)
        note.plain_text = to_plain_text(note.content_json)
        await self.notes.mark_updated(note)
        await self.db.commit()
        await self.db.refresh(note)
        return note

    # --- collaboration -----------------------------------------------------------------------

    async def invite(
        self, user: User, note_id: uuid.UUID, payload: CollaboratorInvite
    ) -> NoteCollaborator:
        note = await self.get_note(user, note_id)
        if note.user_id != user.id:
            raise Conflict("Only the owner can share this note.", code="NOTE_NOT_OWNER")
        email = payload.email.lower()
        if email == user.email.lower():
            raise ValidationFailed("That is you.", details={"fields": {"email": ["That is you"]}})
        # A share names a specific address, so it binds to that account wherever it lives
        # (every personal signup is its own tenant).
        match = await self.db.scalar(select(User).where(User.email == email))
        existing = next((c for c in note.collaborators if c.email == email), None)
        if existing is not None:
            existing.role = payload.role
            if existing.user_id is None and match is not None:
                existing.user_id = match.id
            await self.db.commit()
            return existing
        row = NoteCollaborator(
            note_id=note.id,
            user_id=match.id if match else None,
            email=email,
            role=payload.role,
            invited_by=user.id,
        )
        self.db.add(row)
        await self.db.flush()
        if match is not None:
            await NotificationService(self.db).notify(
                match,
                NotificationKind.note_shared,
                f"{user.display_name} shared a note with you",
                body=note.title or "Untitled",
                href=f"/app/notes/{note.id}",
                dedupe_key=f"note:{note.id}:shared:{match.id}",
                commit=False,
            )
        await self.db.commit()
        await self.db.refresh(note)
        return row

    async def update_collaborator(
        self, user: User, note_id: uuid.UUID, collaborator_id: uuid.UUID, role: CollaboratorRole
    ) -> NoteCollaborator:
        note = await self.get_note(user, note_id)
        if note.user_id != user.id:
            raise Conflict("Only the owner can change access.", code="NOTE_NOT_OWNER")
        row = next((c for c in note.collaborators if c.id == collaborator_id), None)
        if row is None:
            raise NotFound("Collaborator not found.")
        row.role = role
        await self.db.commit()
        return row

    async def remove_collaborator(
        self, user: User, note_id: uuid.UUID, collaborator_id: uuid.UUID
    ) -> None:
        note = await self.get_note(user, note_id)
        row = next((c for c in note.collaborators if c.id == collaborator_id), None)
        if row is None:
            raise NotFound("Collaborator not found.")
        # Owners remove anyone; a collaborator may remove themselves (leave).
        if note.user_id != user.id and row.user_id != user.id:
            raise Conflict("Only the owner can change access.", code="NOTE_NOT_OWNER")
        await self.db.delete(row)
        await self.db.commit()

    async def _resolve_tags(self, user: User, tag_ids: list[uuid.UUID]) -> list[Tag]:
        unique = list(dict.fromkeys(tag_ids))
        tags = await self.tags.get_many(unique, user.id)
        if len(tags) != len(unique):
            raise NotFound("One or more tags were not found.")
        return tags

    async def trash_note(self, user: User, note_id: uuid.UUID) -> Note:
        note = await self.get_note(user, note_id)
        if note.deleted_at is None:
            note.deleted_at = utcnow()
            await self.db.commit()
        return note

    async def restore_note(self, user: User, note_id: uuid.UUID) -> Note:
        note = await self.get_note(user, note_id)
        note.deleted_at = None
        await self.db.commit()
        return note

    async def purge_note(self, user: User, note_id: uuid.UUID) -> None:
        note = await self.get_note(user, note_id)
        if note.deleted_at is None:
            raise Conflict(
                "Move the note to the trash before deleting it permanently.",
                code="NOTE_NOT_IN_TRASH",
            )
        await self.notes.purge(note)
        await self.db.commit()

    async def duplicate_note(self, user: User, note_id: uuid.UUID) -> Note:
        source = await self.get_note(user, note_id)
        copy_note = await self.notes.create(
            user,
            title=f"{source.title} (copy)" if source.title else "Untitled (copy)",
            content_json=copy.deepcopy(source.content_json),
            plain_text=source.plain_text,
            folder_id=source.folder_id,
            metadata_={"duplicated_from": str(source.id)},
        )
        if source.tags:
            await self.notes.set_tags(copy_note, list(source.tags))
        await self.db.commit()
        await self.db.refresh(copy_note)
        return copy_note

    async def search(self, user: User, q: str, limit: int = 20) -> list[SearchRow]:
        q = " ".join(q.split())
        if not q:
            return []
        return await self.notes.search(user.id, q, limit)
