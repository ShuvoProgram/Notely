"""Import every model here so Alembic autogenerate and Base.metadata see them."""

from app.db.base import Base
from app.models.tenant import Tenant, TenantKind
from app.models.user import AuthIdentity, SignInProvider, User, UserSession

__all__ = ["AuthIdentity", "Base", "SignInProvider", "Tenant", "TenantKind", "User", "UserSession"]
