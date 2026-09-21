from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.note import CollaboratorRole
from app.services.rich_text import is_valid_doc

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


# --- folders ------------------------------------------------------------------------------------


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: uuid.UUID | None = None

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Folder name is required")
        return v


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    parent_id: uuid.UUID | None = None
    position: int | None = Field(default=None, ge=0)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Folder name is required")
        return v


class FolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    position: int
    note_count: int = 0
    created_at: datetime
    updated_at: datetime


# --- tags ---------------------------------------------------------------------------------------


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    color: str | None = None

    @field_validator("name")
    @classmethod
    def _norm(cls, v: str) -> str:
        v = " ".join(v.strip().split())
        if not v:
            raise ValueError("Tag name is required")
        return v

    @field_validator("color")
    @classmethod
    def _color(cls, v: str | None) -> str | None:
        if v is not None and not HEX_COLOR.match(v):
            raise ValueError("Color must be #RRGGBB")
        return v.lower() if v else v


class TagUpdate(TagCreate):
    name: str | None = Field(default=None, min_length=1, max_length=60)  # type: ignore[assignment]

    @field_validator("name")
    @classmethod
    def _norm(cls, v: str | None) -> str | None:  # type: ignore[override]
        if v is None:
            return v
        v = " ".join(v.strip().split())
        if not v:
            raise ValueError("Tag name is required")
        return v


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    color: str | None
    note_count: int = 0


# --- notes --------------------------------------------------------------------------------------


def _validate_doc(v: dict[str, Any] | None) -> dict[str, Any] | None:
    if v is not None and not is_valid_doc(v):
        raise ValueError("content_json must be a TipTap document")
    return v


NOTE_COLOR_PRESETS = (
    "default",
    "warm",
    "cream",
    "yellow",
    "green",
    "mint",
    "blue",
    "sky",
    "purple",
    "lavender",
    "pink",
    "rose",
    "gray",
)
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def validate_note_color(v: str) -> str:
    """A preset name or a custom `#rrggbb`. The UI only ever paints a custom colour as a soft
    tint over the surface, so any hex is safe for readability."""
    v = v.strip()
    if v in NOTE_COLOR_PRESETS:
        return v
    if _HEX.match(v):
        return v.lower()
    raise ValueError("Pick one of the preset colours or a #rrggbb value")


# Preset name or "#rrggbb" (see validate_note_color).
NoteColor = str


class BulkIds(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class NoteCreate(BaseModel):
    title: str = Field(default="", max_length=300)
    content_json: dict[str, Any] | None = None
    folder_id: uuid.UUID | None = None
    tag_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)

    @field_validator("content_json")
    @classmethod
    def _doc(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_doc(v)


class NoteUpdate(BaseModel):
    """Partial update. `expected_version` enables optimistic concurrency for autosave."""

    title: str | None = Field(default=None, max_length=300)
    content_json: dict[str, Any] | None = None
    folder_id: uuid.UUID | None = None
    clear_folder: bool = False
    tag_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    is_favorite: bool | None = None
    archived: bool | None = None
    color: NoteColor | None = None

    @field_validator("color")
    @classmethod
    def _color(cls, v: str | None) -> str | None:
        return None if v is None else validate_note_color(v)

    reminder_at: datetime | None = None
    clear_reminder: bool = False
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("content_json")
    @classmethod
    def _doc(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_doc(v)


class ChecklistProgress(BaseModel):
    done: int
    total: int


InvitationStatus = Literal["pending", "accepted", "expired"]


class CollaboratorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: CollaboratorRole
    user_id: uuid.UUID | None
    display_name: str | None = None
    status: InvitationStatus = "pending"
    invited_at: datetime | None = None
    accepted_at: datetime | None = None
    invite_expires_at: datetime | None = None
    created_at: datetime


class DeliveryOut(BaseModel):
    """What happened to the invitation email. `sent=False` carries the real reason."""

    sent: bool
    error: str | None = None


class InviteResult(BaseModel):
    collaborator: CollaboratorOut
    delivery: DeliveryOut


class InvitationOut(BaseModel):
    """Public view of an invitation, for the accept page (no secrets, no note body)."""

    note_id: uuid.UUID
    note_title: str
    inviter_name: str
    email: str
    role: CollaboratorRole
    status: InvitationStatus
    expires_at: datetime | None


class CollaboratorInvite(BaseModel):
    email: EmailStr
    role: CollaboratorRole = CollaboratorRole.viewer
    # Re-send the email for a pending invitation (new link, new expiry). Without it, inviting
    # an address that already has a pending invitation is a 409, so a double click never
    # sends two emails.
    resend: bool = False


class CollaboratorUpdate(BaseModel):
    role: CollaboratorRole


class NoteVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    note_version: int
    title: str
    plain_text: str
    reason: str
    created_at: datetime


class NoteVersionDetail(NoteVersionOut):
    content_json: dict[str, Any]


class NoteSummary(BaseModel):
    """List representation: no body, just enough for a row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    excerpt: str
    folder_id: uuid.UUID | None
    tags: list[TagOut]
    is_favorite: bool
    archived_at: datetime | None
    deleted_at: datetime | None
    version: int
    color: NoteColor = "default"
    reminder_at: datetime | None = None
    checklist: ChecklistProgress | None = None
    # Who else can see it; owners see their invitees, invitees see they are a guest.
    shared: bool = False
    access: Literal["owner", "editor", "viewer"] = "owner"
    created_at: datetime
    updated_at: datetime


class NoteOut(NoteSummary):
    content_json: dict[str, Any]
    plain_text: str
    summary: str | None
    metadata: dict[str, Any] = Field(default_factory=dict)
    collaborators: list[CollaboratorOut] = Field(default_factory=list)


NoteView = Literal["active", "favorites", "archived", "trash", "shared", "all"]


class NoteListQuery(BaseModel):
    view: NoteView = "active"
    folder_id: uuid.UUID | None = None
    tag_id: uuid.UUID | None = None
    q: str | None = Field(default=None, max_length=200)
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=100)


class SearchHit(BaseModel):
    source: str  # "notely" or a provider id
    kind: str
    id: str
    title: str
    snippet: str
    url: str | None
    score: float
    updated_at: str | None


class SearchSource(BaseModel):
    source: str
    ok: bool
    count: int
    error: str | None = None


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
    sources: list[SearchSource]
