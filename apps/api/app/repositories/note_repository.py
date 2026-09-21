"""Persistence for notes, folders and tags. Every query is scoped to the owning user."""

from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models.note import Folder, Note, NoteCollaborator, NoteTag, Tag
from app.models.user import User


def encode_cursor(updated_at: datetime, note_id: uuid.UUID) -> str:
    raw = f"{updated_at.isoformat()}|{note_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID] | None:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        ts, nid = raw.split("|", 1)
        return datetime.fromisoformat(ts), uuid.UUID(nid)
    except Exception:
        return None


@dataclass(frozen=True)
class SearchRow:
    note: Note
    score: float


class FolderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(self, user_id: uuid.UUID) -> list[tuple[Folder, int]]:
        counts = (
            select(Note.folder_id, func.count(Note.id).label("n"))
            .where(Note.user_id == user_id, Note.deleted_at.is_(None))
            .group_by(Note.folder_id)
            .subquery()
        )
        stmt = (
            select(Folder, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.folder_id == Folder.id)
            .where(Folder.user_id == user_id)
            .order_by(Folder.position, Folder.name)
        )
        result = await self.session.execute(stmt)
        return [(row[0], int(row[1])) for row in result.all()]

    async def get(self, folder_id: uuid.UUID, user_id: uuid.UUID) -> Folder | None:
        return await self.session.scalar(
            select(Folder).where(Folder.id == folder_id, Folder.user_id == user_id)
        )

    async def name_exists(
        self,
        user_id: uuid.UUID,
        parent_id: uuid.UUID | None,
        name: str,
        exclude: uuid.UUID | None = None,
    ) -> bool:
        stmt = select(Folder.id).where(
            Folder.user_id == user_id,
            Folder.parent_id.is_(parent_id) if parent_id is None else Folder.parent_id == parent_id,
            func.lower(Folder.name) == name.lower(),
        )
        if exclude is not None:
            stmt = stmt.where(Folder.id != exclude)
        return (await self.session.scalar(stmt)) is not None

    async def create(self, user: User, name: str, parent_id: uuid.UUID | None) -> Folder:
        max_pos = await self.session.scalar(
            select(func.coalesce(func.max(Folder.position), -1)).where(
                Folder.user_id == user.id,
                Folder.parent_id.is_(None) if parent_id is None else Folder.parent_id == parent_id,
            )
        )
        folder = Folder(
            tenant_id=user.tenant_id,
            user_id=user.id,
            name=name,
            parent_id=parent_id,
            position=int(max_pos or -1) + 1,
        )
        self.session.add(folder)
        await self.session.flush()
        return folder

    async def delete(self, folder: Folder) -> None:
        await self.session.delete(folder)


class TagRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(self, user_id: uuid.UUID) -> list[tuple[Tag, int]]:
        counts = (
            select(NoteTag.tag_id, func.count(NoteTag.note_id).label("n"))
            .join(Note, Note.id == NoteTag.note_id)
            .where(NoteTag.user_id == user_id, Note.deleted_at.is_(None))
            .group_by(NoteTag.tag_id)
            .subquery()
        )
        stmt = (
            select(Tag, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.tag_id == Tag.id)
            .where(Tag.user_id == user_id)
            .order_by(Tag.name)
        )
        result = await self.session.execute(stmt)
        return [(row[0], int(row[1])) for row in result.all()]

    async def get(self, tag_id: uuid.UUID, user_id: uuid.UUID) -> Tag | None:
        return await self.session.scalar(
            select(Tag).where(Tag.id == tag_id, Tag.user_id == user_id)
        )

    async def get_many(self, tag_ids: list[uuid.UUID], user_id: uuid.UUID) -> list[Tag]:
        if not tag_ids:
            return []
        result = await self.session.scalars(
            select(Tag).where(Tag.user_id == user_id, Tag.id.in_(tag_ids))
        )
        return list(result)

    async def get_by_name(self, user_id: uuid.UUID, name: str) -> Tag | None:
        return await self.session.scalar(
            select(Tag).where(Tag.user_id == user_id, func.lower(Tag.name) == name.lower())
        )

    async def create(self, user: User, name: str, color: str | None) -> Tag:
        tag = Tag(tenant_id=user.tenant_id, user_id=user.id, name=name, color=color)
        self.session.add(tag)
        await self.session.flush()
        return tag

    async def delete(self, tag: Tag) -> None:
        await self.session.delete(tag)


class NoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base(self, user_id: uuid.UUID) -> Select[tuple[Note]]:
        return select(Note).where(Note.user_id == user_id)

    async def get(self, note_id: uuid.UUID, user_id: uuid.UUID) -> Note | None:
        return await self.session.scalar(self._base(user_id).where(Note.id == note_id))

    async def get_shared(self, note_id: uuid.UUID, user_id: uuid.UUID) -> Note | None:
        """A note someone else owns but shared with this user (by matched account)."""
        return await self.session.scalar(
            select(Note).where(
                Note.id == note_id,
                Note.id.in_(
                    select(NoteCollaborator.note_id).where(NoteCollaborator.user_id == user_id)
                ),
            )
        )

    async def create(self, user: User, **fields: Any) -> Note:
        note = Note(tenant_id=user.tenant_id, user_id=user.id, **fields)
        self.session.add(note)
        await self.session.flush()
        return note

    async def list_notes(
        self,
        user_id: uuid.UUID,
        *,
        view: str,
        folder_id: uuid.UUID | None,
        tag_id: uuid.UUID | None,
        q: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Note], str | None]:
        if view == "shared":
            # Notes others shared with me (matched by account), never my own.
            stmt = select(Note).where(
                Note.user_id != user_id,
                Note.deleted_at.is_(None),
                Note.id.in_(
                    select(NoteCollaborator.note_id).where(NoteCollaborator.user_id == user_id)
                ),
            )
        else:
            stmt = self._base(user_id)
        if view == "shared":
            pass
        elif view == "trash":
            stmt = stmt.where(Note.deleted_at.is_not(None))
        else:
            stmt = stmt.where(Note.deleted_at.is_(None))
            if view == "active":
                stmt = stmt.where(Note.archived_at.is_(None))
            elif view == "favorites":
                stmt = stmt.where(Note.archived_at.is_(None), Note.is_favorite.is_(True))
            elif view == "archived":
                stmt = stmt.where(Note.archived_at.is_not(None))
        if folder_id is not None:
            stmt = stmt.where(Note.folder_id == folder_id)
        if tag_id is not None:
            stmt = stmt.where(Note.id.in_(select(NoteTag.note_id).where(NoteTag.tag_id == tag_id)))
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(Note.title.ilike(like), Note.plain_text.ilike(like)))
        if cursor:
            decoded = decode_cursor(cursor)
            if decoded:
                ts, nid = decoded
                stmt = stmt.where(
                    or_(Note.updated_at < ts, (Note.updated_at == ts) & (Note.id < nid))
                )
        stmt = stmt.order_by(Note.updated_at.desc(), Note.id.desc()).limit(limit + 1)
        rows = list(await self.session.scalars(stmt))
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            next_cursor = encode_cursor(last.updated_at, last.id)
        return rows, next_cursor

    async def search(self, user_id: uuid.UUID, q: str, limit: int = 20) -> list[SearchRow]:
        """Full-text search on PostgreSQL; ILIKE fallback elsewhere (tests)."""
        dialect = self.session.bind.dialect.name if self.session.bind is not None else "sqlite"
        if dialect == "postgresql":
            tsquery = func.websearch_to_tsquery("english", q)
            vector = text("notes.search_vector")
            rank = func.ts_rank_cd(vector, tsquery)
            stmt = (
                select(Note, rank.label("score"))
                .where(Note.user_id == user_id, Note.deleted_at.is_(None))
                .where(
                    text("notes.search_vector @@ websearch_to_tsquery('english', :q)").bindparams(
                        q=q
                    )
                )
                .order_by(rank.desc(), Note.updated_at.desc())
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            return [SearchRow(note=row[0], score=float(row[1])) for row in result.all()]

        like = f"%{q}%"
        stmt = (
            select(Note)
            .where(Note.user_id == user_id, Note.deleted_at.is_(None))
            .where(or_(Note.title.ilike(like), Note.plain_text.ilike(like)))
            .order_by(Note.updated_at.desc())
            .limit(limit)
        )
        notes = list(await self.session.scalars(stmt))
        lowered = q.lower()
        return [SearchRow(note=n, score=1.0 if lowered in n.title.lower() else 0.5) for n in notes]

    async def set_tags(self, note: Note, tags: list[Tag]) -> None:
        await self.session.execute(delete(NoteTag).where(NoteTag.note_id == note.id))
        for tag in tags:
            self.session.add(NoteTag(note_id=note.id, tag_id=tag.id, user_id=note.user_id))
        await self.session.flush()
        await self.session.refresh(note, attribute_names=["tags"])

    async def purge(self, note: Note) -> None:
        await self.session.delete(note)

    async def purge_trash_older_than(self, cutoff: datetime) -> int:
        result = await self.session.execute(delete(Note).where(Note.deleted_at < cutoff))
        return int(getattr(result, "rowcount", 0) or 0)

    async def mark_updated(self, note: Note) -> None:
        note.updated_at = utcnow()
        note.version += 1
