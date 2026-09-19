"""Import every model here so Alembic autogenerate and Base.metadata see them."""

from app.db.base import Base
from app.models.ai import (
    AIApproval,
    AIMessage,
    AIRun,
    AIThread,
    AIToolCall,
    ApprovalStatus,
    AuditEvent,
    MessageRole,
    RiskLevel,
    RunStatus,
    ToolCallStatus,
)
from app.models.integration import (
    ConnectionStatus,
    ExternalItem,
    Integration,
    UserConnection,
    WebhookEvent,
)
from app.models.note import Folder, Note, NoteTag, Tag
from app.models.task import Task, TaskPriority, TaskSource, TaskStatus
from app.models.tenant import Tenant, TenantKind
from app.models.user import AuthIdentity, SignInProvider, User, UserSession

__all__ = [
    "AIApproval",
    "AIMessage",
    "AIRun",
    "AIThread",
    "AIToolCall",
    "ApprovalStatus",
    "AuditEvent",
    "AuthIdentity",
    "Base",
    "ConnectionStatus",
    "ExternalItem",
    "Folder",
    "Integration",
    "MessageRole",
    "Note",
    "NoteTag",
    "RiskLevel",
    "RunStatus",
    "SignInProvider",
    "Tag",
    "Task",
    "TaskPriority",
    "TaskSource",
    "TaskStatus",
    "Tenant",
    "TenantKind",
    "ToolCallStatus",
    "User",
    "UserConnection",
    "UserSession",
    "WebhookEvent",
]
