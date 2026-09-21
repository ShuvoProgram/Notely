"""Connections: the one place that turns providers into user-owned, encrypted, status-tracked links.

Flow (OAuth):  start → provider consent → callback (state validated, code exchanged) → encrypt →
create/refresh connection → provider.complete_connection → connected.
Flow (token):  connect(config, token) → encrypt → provider.complete_connection → connected.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.base import ToolSpec
from app.core import metrics
from app.core.config import Settings
from app.core.exceptions import APIError, NotFound, ValidationFailed
from app.core.logging import get_logger
from app.core.oauth import (
    OAuthClient,
    OAuthTokens,
    callback_slot,
    callback_uri,
    consume_oauth_state,
)
from app.db.base import utcnow
from app.integrations.base.errors import ProviderError, ProviderErrorKind
from app.integrations.base.provider import (
    AuthType,
    ConnectionTest,
    IntegrationProvider,
    ProviderContext,
    TestStep,
)
from app.integrations.mcp_server.provider import MCPModeAdapter, MCPServerProvider
from app.integrations.registry import get_provider, get_providers
from app.models.ai import RiskLevel
from app.models.integration import (
    ConnectionStatus,
    ExternalItem,
    Integration,
    UserConnection,
)
from app.models.notification import NotificationKind
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.credential_vault import CredentialVault
from app.services.notification_service import NotificationService

log = get_logger(__name__)

# Statuses in which the connection can serve tools/search.
USABLE = {ConnectionStatus.connected, ConnectionStatus.syncing}
# Refresh OAuth tokens this long before they expire.
REFRESH_LEEWAY = timedelta(minutes=5)


@dataclass(frozen=True)
class MarketplaceEntry:
    provider: IntegrationProvider
    configured: bool
    connection: UserConnection | None


def status_from_error(error: ProviderError) -> ConnectionStatus:
    if error.kind in (ProviderErrorKind.expired, ProviderErrorKind.auth_failed):
        return ConnectionStatus.expired
    if error.kind in (
        ProviderErrorKind.permission_denied,
        ProviderErrorKind.admin_approval_required,
    ):
        return ConnectionStatus.needs_attention
    if error.kind in (ProviderErrorKind.invalid_request, ProviderErrorKind.misconfigured):
        return ConnectionStatus.needs_attention
    return ConnectionStatus.error


# auth_type of connections made through a vendor's official MCP server
MCP_AUTH = "mcp"


def denial_message(provider: IntegrationProvider, error: str | None) -> str:
    """What to record when the vendor sends the user back without a code. Google (and Microsoft)
    return the same `access_denied` whether the user pressed Cancel or the deployment's app is
    still in *Testing* on the vendor's console — say so, because only an operator can fix the
    latter and the user would otherwise keep retrying."""
    vendor = callback_slot(provider)
    if error == "access_denied" and vendor in ("google", "microsoft"):
        console = "Google Cloud Console" if vendor == "google" else "the Microsoft Entra portal"
        return (
            f"{provider.manifest.name} refused the request (access_denied). If you cancelled, "
            "just try again. If you saw “Access blocked: Notely has not completed the "
            f"verification process”, this deployment's app is still in testing mode on {console}"
            " and only listed test users can connect — the administrator needs to publish it "
            "(docs/oauth-setup.md)."
        )
    if error == "access_denied":
        return "Access wasn't granted on the vendor's screen."
    return f"The vendor returned {error or 'no authorization code'}."


class ConnectionService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.vault = CredentialVault(settings)
        self.audit = AuditService(db)

    # --- catalog ---------------------------------------------------------------------------------

    async def ensure_catalog(self) -> None:
        """Upsert one `integrations` row per registered provider (idempotent, runs at startup)."""
        existing = {row.provider: row for row in await self.db.scalars(select(Integration))}
        for provider in get_providers().values():
            m = provider.manifest
            row = existing.get(m.id)
            if row is None:
                self.db.add(
                    Integration(
                        provider=m.id,
                        name=m.name,
                        category=m.category,
                        logo_url=m.logo_url,
                        description=m.description,
                    )
                )
            else:
                row.name, row.category, row.logo_url, row.description = (
                    m.name,
                    m.category,
                    m.logo_url,
                    m.description,
                )
        await self.db.commit()

    async def marketplace(self, user: User) -> list[MarketplaceEntry]:
        rows = {
            c.provider: c
            for c in await self.db.scalars(
                select(UserConnection).where(UserConnection.user_id == user.id)
            )
        }
        enabled = {
            row.provider
            for row in await self.db.scalars(select(Integration).where(Integration.enabled))
        }
        entries = []
        for provider in get_providers().values():
            if enabled and provider.manifest.id not in enabled:
                continue
            # Only vendors people can actually click Connect on (or already connected) are
            # listed; a vendor with no OAuth app on this deployment simply isn't offered.
            if not provider.connect_methods(self.settings) and provider.manifest.id not in rows:
                continue
            entries.append(
                MarketplaceEntry(
                    provider=provider,
                    configured=provider.is_configured(self.settings),
                    connection=rows.get(provider.manifest.id),
                )
            )
        return entries

    def provider_or_404(self, provider_id: str) -> IntegrationProvider:
        provider = get_provider(provider_id)
        if provider is None:
            raise NotFound("Unknown integration.")
        return provider

    def adapter(self, conn: UserConnection) -> IntegrationProvider:
        """The object that talks to the vendor for this connection: the REST adapter, or — for
        connections made through the vendor's official MCP server — an MCP-mode adapter that
        keeps the vendor's identity (ids, labels, audit) but speaks MCP."""
        provider = self.provider_or_404(conn.provider)
        if conn.auth_type == MCP_AUTH and not isinstance(provider, MCPServerProvider):
            return MCPModeAdapter(provider.manifest)
        return provider

    def _redirect_uri(self, provider: IntegrationProvider | str) -> str:
        slot = provider if isinstance(provider, str) else callback_slot(provider)
        return callback_uri(self.settings, f"/oauth/{slot}/callback")

    async def _integration_row(self, provider_id: str) -> Integration:
        row = await self.db.scalar(select(Integration).where(Integration.provider == provider_id))
        if row is None:
            await self.ensure_catalog()
            row = await self.db.scalar(
                select(Integration).where(Integration.provider == provider_id)
            )
        if row is None or not row.enabled:
            raise NotFound("This integration is not available.")
        return row

    # --- lookups ---------------------------------------------------------------------------------

    async def get_connection(self, user: User, connection_id: uuid.UUID) -> UserConnection:
        conn = await self.db.scalar(
            select(UserConnection).where(
                UserConnection.id == connection_id, UserConnection.user_id == user.id
            )
        )
        if conn is None:
            raise NotFound("Connection not found.")
        return conn

    async def get_by_provider(self, user: User, provider_id: str) -> UserConnection | None:
        return await self.db.scalar(
            select(UserConnection).where(
                UserConnection.user_id == user.id, UserConnection.provider == provider_id
            )
        )

    async def list_usable(self, user: User) -> list[UserConnection]:
        return list(
            await self.db.scalars(
                select(UserConnection).where(
                    UserConnection.user_id == user.id, UserConnection.status.in_(list(USABLE))
                )
            )
        )

    async def _get_or_create(self, user: User, provider: IntegrationProvider) -> UserConnection:
        conn = await self.get_by_provider(user, provider.manifest.id)
        if conn is None:
            integration = await self._integration_row(provider.manifest.id)
            conn = UserConnection(
                tenant_id=user.tenant_id,
                user_id=user.id,
                integration_id=integration.id,
                provider=provider.manifest.id,
                auth_type=provider.manifest.auth.value,
                status=ConnectionStatus.pending,
            )
            self.db.add(conn)
            await self.db.flush()
        return conn

    def context(self, user: User, conn: UserConnection) -> ProviderContext:
        return ProviderContext(
            user=user,
            db=self.db,
            connection=conn,
            credentials=self.vault.load(conn),
            settings=self.settings,
        )

    # --- OAuth ----------------------------------------------------------------------------------

    def _oauth_client(
        self, provider: IntegrationProvider, scopes: list[str] | None = None
    ) -> OAuthClient:
        config = provider.oauth_config(self.settings)
        if config is None:
            raise ProviderError(
                ProviderErrorKind.misconfigured, provider=provider.manifest.id
            ).as_api_error()
        from dataclasses import replace

        # State is keyed by the callback slot the vendor will send the user back to.
        config = replace(config, provider_id=callback_slot(provider))
        if scopes:
            config = replace(config, scopes=tuple(scopes))
        return OAuthClient(config, self._redirect_uri(provider))

    async def start_oauth(
        self,
        user: User,
        provider_id: str,
        *,
        selected_scopes: list[str] | None,
        method: str | None = None,
        server_url: str | None = None,
    ) -> str:
        """Begin a browser OAuth flow and return the URL to send the user to.

        `method` picks the door: `oauth` (the deployment's own vendor app) or `mcp` (the
        vendor's official MCP server, or `server_url` for the generic MCP entry, with a
        dynamically registered client). Default: own app when configured, else MCP."""
        provider = self.provider_or_404(provider_id)
        methods = provider.connect_methods(self.settings)
        if method is None:
            method = "oauth" if "oauth" in methods else "mcp" if "mcp" in methods else ""
        if method == "mcp" or (server_url and isinstance(provider, MCPServerProvider)):
            return await self._start_mcp_oauth(user, provider, server_url)
        if method != "oauth" or "oauth" not in methods:
            raise ValidationFailed("This integration cannot connect with OAuth here.")
        scopes = provider.scopes_for(selected_scopes)
        conn = await self._get_or_create(user, provider)
        if conn.status == ConnectionStatus.disconnected or conn.status == ConnectionStatus.pending:
            conn.status = ConnectionStatus.connecting
        conn.scopes = scopes
        conn.auth_type = AuthType.oauth2.value
        await self.db.commit()
        client = self._oauth_client(provider, scopes)
        return await client.begin(
            context={
                "user_id": str(user.id),
                "connection_id": str(conn.id),
                "mode": "oauth",
                "provider_id": provider.manifest.id,
            }
        )

    async def _start_mcp_oauth(
        self, user: User, provider: IntegrationProvider, server_url: str | None
    ) -> str:
        from app.mcp import oauth as mcp_oauth

        url = (server_url or provider.manifest.mcp_server_url or "").strip()
        if not url.startswith("https://") and not (
            url.startswith("http://") and not self.settings.is_production
        ):
            raise ValidationFailed(
                "Enter the server's https URL.", details={"fields": {"server_url": ["Invalid"]}}
            )
        conn = await self._get_or_create(user, provider)
        conn.auth_type = MCP_AUTH
        conn.metadata_ = {**conn.metadata_, "mcp_url": url}
        if isinstance(provider, MCPServerProvider):
            conn.config = {**conn.config, "server_url": url}
        conn.status = ConnectionStatus.connecting
        await self.db.commit()
        try:
            auth = await mcp_oauth.discover(url)
        except ProviderError as exc:
            await self._fail(conn, exc, status=ConnectionStatus.error)
            raise exc.as_api_error() from exc
        if auth is None:
            # Public server: nothing to authorise; connect right away.
            self.vault.store_token(conn, None)
            await self._finish_connect(user, self.adapter(conn), conn)
            base = f"{self.settings.frontend_origin}/app/connections"
            return f"{base}/{conn.provider}?connected=1"
        try:
            config = await mcp_oauth.dynamic_client(
                self.db, self.settings, auth, self._redirect_uri(conn.provider), conn.provider
            )
        except ProviderError as exc:
            await self._fail(conn, exc, status=ConnectionStatus.error)
            raise exc.as_api_error() from exc
        conn.scopes = list(auth.scopes)
        await self.db.commit()
        client = OAuthClient(config, self._redirect_uri(conn.provider))
        return await client.begin(
            context={
                "user_id": str(user.id),
                "connection_id": str(conn.id),
                "mode": "mcp",
                "server_url": url,
                "provider_id": conn.provider,
            }
        )

    async def complete_oauth(
        self,
        user: User,
        slot: str,
        *,
        code: str | None,
        state: str | None,
        error: str | None,
    ) -> UserConnection:
        """`slot` is the callback the vendor sent the user back to (a provider id, or a vendor
        family such as `google`); the state record names the actual provider."""
        record = await consume_oauth_state(slot, state, self._redirect_uri(slot))
        return await self.complete_oauth_record(user, slot, record, code=code, error=error)

    async def complete_oauth_record(
        self,
        user: User,
        slot: str,
        record: dict[str, Any],
        *,
        code: str | None,
        error: str | None,
    ) -> UserConnection:
        """Second half of `complete_oauth`, for callers that validated the state themselves."""
        ctx_info = record.get("context") or {}
        if ctx_info.get("user_id") != str(user.id):
            from app.core.exceptions import InvalidOAuthState

            raise InvalidOAuthState()
        provider_id = str(ctx_info.get("provider_id") or slot)
        try:
            return await self._complete_oauth(user, provider_id, record, code=code, error=error)
        except APIError as exc:
            # So the callback route can send the user back to the right provider page.
            exc.details.setdefault("provider_id", provider_id)
            raise

    async def _complete_oauth(
        self,
        user: User,
        provider_id: str,
        record: dict[str, Any],
        *,
        code: str | None,
        error: str | None,
    ) -> UserConnection:
        ctx_info = record.get("context") or {}
        provider = self.provider_or_404(provider_id)
        conn = await self._get_or_create(user, provider)
        if ctx_info.get("mode") == "mcp":
            from app.mcp import oauth as mcp_oauth

            url = str(ctx_info.get("server_url") or conn.metadata_.get("mcp_url") or "")
            auth = await mcp_oauth.discover(url)
            if auth is None:
                raise ProviderError(
                    ProviderErrorKind.misconfigured,
                    "server no longer requires auth",
                    provider=provider_id,
                ).as_api_error()
            client = OAuthClient(
                await mcp_oauth.dynamic_client(
                    self.db, self.settings, auth, self._redirect_uri(provider_id), provider_id
                ),
                self._redirect_uri(provider_id),
            )
            conn.auth_type = MCP_AUTH
            conn.metadata_ = {**conn.metadata_, "mcp_url": url}
        else:
            client = self._oauth_client(provider)
        if error or not code:
            metrics.oauth_failures.labels(provider_id, "authorize").inc()
            await self._fail(
                conn,
                ProviderError(
                    ProviderErrorKind.auth_failed, error or "denied", provider=provider_id
                ),
                status=ConnectionStatus.error,
            )
            conn.last_error = denial_message(provider, error)
            await self.db.commit()
            api_error = ProviderError(
                ProviderErrorKind.auth_failed, provider=provider_id
            ).as_api_error()
            # The vendor's own error code rides along so the page can say what actually happened.
            api_error.details["reason"] = error or "denied"
            raise api_error
        try:
            tokens = await client.exchange_code(code, record.get("verifier"))
        except Exception:
            metrics.oauth_failures.labels(provider_id, "exchange").inc()
            raise
        self.vault.store_tokens(conn, tokens)
        conn.token_expires_at = (
            utcnow() + timedelta(seconds=int(tokens.expires_in)) if tokens.expires_in else None
        )
        if tokens.scope:
            conn.scopes = tokens.scope.replace(",", " ").split()
        await self._finish_connect(user, self.adapter(conn), conn)
        return conn

    async def refresh_if_needed(self, user: User, conn: UserConnection) -> None:
        """Refresh an OAuth token nearing expiry. Marks the connection expired if that fails."""
        if conn.token_expires_at is None:
            return
        if conn.token_expires_at - utcnow() > REFRESH_LEEWAY:
            return
        provider = self.adapter(conn)
        try:
            tokens = await provider.refresh_credentials(self.context(user, conn))
        except ProviderError as exc:
            await self._fail(conn, exc)
            await NotificationService(self.db).notify(
                user,
                NotificationKind.integration_auth_required,
                f"{provider.manifest.name} needs to be reconnected",
                body="Its authorization expired. Reconnect to keep using it.",
                href=f"/app/settings/connections/{conn.provider}",
                dedupe_key=f"conn:{conn.id}:auth:{conn.last_checked_at}",
            )
            raise
        if tokens is None:
            return
        self._apply_tokens(conn, tokens)
        await self.db.commit()

    def _apply_tokens(self, conn: UserConnection, tokens: OAuthTokens) -> None:
        # Refresh-token rotation: keep the old refresh token if the provider didn't send one.
        current = self.vault.load(conn)
        merged = OAuthTokens(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token or current.refresh_token,
            expires_in=tokens.expires_in,
            id_token=None,
            scope=tokens.scope,
            raw={},
        )
        self.vault.store_tokens(conn, merged)
        conn.token_expires_at = (
            utcnow() + timedelta(seconds=int(tokens.expires_in)) if tokens.expires_in else None
        )

    async def _finish_connect(
        self, user: User, provider: IntegrationProvider, conn: UserConnection
    ) -> None:
        try:
            identity = await provider.complete_connection(self.context(user, conn))
        except ProviderError as exc:
            await self._fail(conn, exc, status=ConnectionStatus.error)
            raise exc.as_api_error() from exc
        conn.external_account_id = identity.external_account_id
        conn.external_account_name = identity.external_account_name
        conn.metadata_ = {**conn.metadata_, **identity.metadata}
        conn.status = ConnectionStatus.connected
        conn.last_error = None
        conn.last_error_code = None
        conn.last_checked_at = utcnow()
        conn.disconnected_at = None
        await NotificationService(self.db).notify(
            user,
            NotificationKind.integration_connected,
            f"{provider.manifest.name} connected",
            body=f"Signed in as {conn.external_account_name or 'your account'}.",
            href=f"/app/settings/connections/{conn.provider}",
            dedupe_key=f"conn:{conn.id}:connected:{utcnow().isoformat()}",
            commit=False,
        )
        await self.audit.record(
            user,
            provider=conn.provider,
            action="connect",
            risk_level=RiskLevel.write,
            status="completed",
            connection_id=conn.id,
            request_metadata={"auth": conn.auth_type, "scopes": conn.scopes},
        )
        await self.db.commit()

    # --- health ----------------------------------------------------------------------------------

    async def test(self, user: User, conn: UserConnection) -> ConnectionTest:
        provider = self.adapter(conn)
        if conn.status == ConnectionStatus.disconnected:
            return ConnectionTest([TestStep("Connection", False, "Not connected")])
        try:
            await self.refresh_if_needed(user, conn)
            result = await provider.test_connection(self.context(user, conn))
        except ProviderError as exc:
            await self._fail(conn, exc)
            title, body = exc.user_message()
            return ConnectionTest([TestStep(title, False, body)])
        conn.last_checked_at = utcnow()
        if result.healthy:
            if conn.status in (ConnectionStatus.error, ConnectionStatus.needs_attention):
                conn.status = ConnectionStatus.connected
            conn.last_error = None
            conn.last_error_code = None
        else:
            failed = next((s for s in result.steps if not s.ok), None)
            conn.status = (
                ConnectionStatus.expired
                if failed and failed.name == "Authentication"
                else ConnectionStatus.needs_attention
            )
            conn.last_error = failed.detail if failed else "Check failed"
        await self.db.commit()
        return result

    async def _fail(
        self, conn: UserConnection, error: ProviderError, *, status: ConnectionStatus | None = None
    ) -> None:
        conn.status = status or status_from_error(error)
        conn.last_error = error.user_message()[1]
        conn.last_error_code = error.kind.value
        conn.last_checked_at = utcnow()
        await self.db.commit()

    async def record_tool_failure(self, conn: UserConnection, error: ProviderError) -> None:
        if error.kind in (
            ProviderErrorKind.expired,
            ProviderErrorKind.auth_failed,
            ProviderErrorKind.permission_denied,
            ProviderErrorKind.admin_approval_required,
        ):
            await self._fail(conn, error)

    # --- permissions / config ----------------------------------------------------------------

    async def update_config(
        self, user: User, conn: UserConnection, *, config: dict[str, Any] | None
    ) -> UserConnection:
        provider = self.provider_or_404(conn.provider)
        if config is not None:
            allowed = {f.key for f in provider.manifest.config_fields if f.kind != "secret"}
            conn.config = {**conn.config, **{k: v for k, v in config.items() if k in allowed}}
        await self.db.commit()
        return conn

    # --- disconnect -------------------------------------------------------------------------------

    async def disconnect(self, user: User, conn: UserConnection, *, purge_data: bool) -> None:
        provider = self.provider_or_404(conn.provider)
        if conn.status != ConnectionStatus.disconnected:
            try:
                await provider.revoke(self.context(user, conn))
            except Exception:  # noqa: BLE001 — revocation is best effort
                log.info("provider_revoke_failed", extra={"provider": conn.provider})
        self.vault.clear(conn)
        conn.status = ConnectionStatus.disconnected
        conn.disconnected_at = utcnow()
        conn.external_account_id = None
        conn.external_account_name = None
        conn.metadata_ = {}
        conn.last_error = None
        conn.last_error_code = None
        purged = 0
        if purge_data:
            purged = await self.purge_local_data(conn)
        await NotificationService(self.db).notify(
            user,
            NotificationKind.integration_disconnected,
            f"{provider.manifest.name} disconnected",
            body="Its credentials were removed from Notely.",
            href=f"/app/settings/connections/{conn.provider}",
            dedupe_key=f"conn:{conn.id}:disconnected:{utcnow().isoformat()}",
            commit=False,
        )
        await self.audit.record(
            user,
            provider=conn.provider,
            action="disconnect",
            risk_level=RiskLevel.write,
            status="completed",
            connection_id=conn.id,
            result_metadata={"purged_items": purged},
        )
        await self.db.commit()

    async def purge_local_data(self, conn: UserConnection) -> int:
        result = await self.db.execute(
            delete(ExternalItem).where(ExternalItem.connection_id == conn.id)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def local_item_count(self, conn: UserConnection) -> int:
        return int(
            await self.db.scalar(
                select(func.count(ExternalItem.id)).where(ExternalItem.connection_id == conn.id)
            )
            or 0
        )

    # --- agent tool discovery -------------------------------------------------------------------

    async def tools_for_user(self, user: User) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for conn in await self.list_usable(user):
            if get_provider(conn.provider) is None:
                continue
            provider = self.adapter(conn)
            try:
                await self.refresh_if_needed(user, conn)
                specs.extend(await provider.tools(self.context(user, conn)))
            except ProviderError as exc:
                await self._fail(conn, exc)
                log.info(
                    "provider_tools_unavailable",
                    extra={"provider": conn.provider, "kind": exc.kind.value},
                )
            except Exception:  # noqa: BLE001
                log.exception("provider_tools_failed", extra={"provider": conn.provider})
        return specs
