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
    UserAISetting,
)
from app.models.automation import (
    Automation,
    AutomationAction,
    AutomationApproval,
    AutomationExecution,
    AutomationExecutionStep,
    AutomationStatus,
    AutomationTemplate,
)
from app.models.integration import (
    ConnectionStatus,
    ExternalItem,
    Integration,
    OAuthDynamicClient,
    UserConnection,
    WebhookEvent,
)
from app.models.note import (
    CollaboratorRole,
    Folder,
    Note,
    NoteCollaborator,
    NoteTag,
    NoteVersion,
    Tag,
)
from app.models.avatar import UserAvatar
from app.models.notification import Notification, NotificationKind
from app.models.task import Task, TaskPriority, TaskSource, TaskStatus
from app.models.tenant import Tenant, TenantKind
from app.models.user import AuthIdentity, SignInProvider, User, UserSession

__all__ = [
    "AIApproval",
    "Automation",
    "AutomationAction",
    "AutomationApproval",
    "AutomationExecution",
    "AutomationExecutionStep",
    "AutomationStatus",
    "AutomationTemplate",
    "AIMessage",
    "AIRun",
    "AIThread",
    "AIToolCall",
    "ApprovalStatus",
    "AuditEvent",
    "UserAISetting",
    "UserAvatar",
    "AuthIdentity",
    "Base",
    "ConnectionStatus",
    "ExternalItem",
    "OAuthDynamicClient",
    "Folder",
    "Integration",
    "MessageRole",
    "CollaboratorRole",
    "Note",
    "NoteCollaborator",
    "NoteVersion",
    "Notification",
    "NotificationKind",
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
