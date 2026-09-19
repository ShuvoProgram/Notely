"""Import every model here so Alembic autogenerate and Base.metadata see them."""

from app.db.base import Base
from app.models.note import Folder, Note, NoteTag, Tag
from app.models.tenant import Tenant, TenantKind
from app.models.user import AuthIdentity, SignInProvider, User, UserSession

__all__ = [
    "AuthIdentity",
    "Base",
    "Folder",
    "Note",
    "NoteTag",
    "SignInProvider",
    "Tag",
    "Tenant",
    "TenantKind",
    "User",
    "UserSession",
]
