"""Provider registry. Adding a provider = adding an adapter module and one line here; the UI
reads provider metadata from the backend, and the AI core never learns provider specifics."""

from __future__ import annotations

from functools import lru_cache

from app.integrations.asana.provider import AsanaProvider
from app.integrations.base.provider import IntegrationProvider
from app.integrations.clickup.provider import ClickUpProvider
from app.integrations.dropbox.provider import DropboxProvider
from app.integrations.google.calendar import GoogleCalendarProvider
from app.integrations.google.drive import GoogleDriveProvider
from app.integrations.google.gmail import GmailProvider
from app.integrations.jira.provider import JiraProvider
from app.integrations.mcp_server.provider import MCPServerProvider
from app.integrations.microsoft.onedrive import OneDriveProvider
from app.integrations.microsoft.outlook import OutlookProvider
from app.integrations.microsoft.teams import TeamsProvider
from app.integrations.notion.provider import NotionProvider
from app.integrations.slack.provider import SlackProvider
from app.integrations.todoist.provider import TodoistProvider

PROVIDER_CLASSES: dict[str, type[IntegrationProvider]] = {
    "slack": SlackProvider,
    "notion": NotionProvider,
    "todoist": TodoistProvider,
    "asana": AsanaProvider,
    "jira": JiraProvider,
    "microsoft_teams": TeamsProvider,
    "outlook": OutlookProvider,
    "dropbox": DropboxProvider,
    "gmail": GmailProvider,
    "google_calendar": GoogleCalendarProvider,
    "google_drive": GoogleDriveProvider,
    "onedrive": OneDriveProvider,
    "clickup": ClickUpProvider,
    "mcp_server": MCPServerProvider,
}


@lru_cache
def get_providers() -> dict[str, IntegrationProvider]:
    from app.integrations.remote_mcp.providers import build_remote_mcp_providers

    providers: dict[str, IntegrationProvider] = {
        pid: cls() for pid, cls in PROVIDER_CLASSES.items() if pid != "mcp_server"
    }
    providers.update(build_remote_mcp_providers())
    providers["mcp_server"] = MCPServerProvider()  # the custom-URL entry stays last
    return providers


def get_provider(provider_id: str) -> IntegrationProvider | None:
    return get_providers().get(provider_id)


def register_provider(provider: IntegrationProvider) -> None:
    """Runtime registration (tests, plugins). Clears the cached mapping."""
    PROVIDER_CLASSES[provider.manifest.id] = type(provider)
    get_providers.cache_clear()
    get_providers()[provider.manifest.id] = provider


def unregister_provider(provider_id: str) -> None:
    PROVIDER_CLASSES.pop(provider_id, None)
    get_providers.cache_clear()
