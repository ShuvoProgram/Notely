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
from app.core.exceptions import NotFound, ValidationFailed
from app.core.logging import get_logger
from app.core.oauth import OAuthClient, OAuthTokens
from app.db.base import utcnow
from app.integrations.base.errors import ProviderError, ProviderErrorKind
from app.integrations.base.provider import (
    AuthType,
    ConnectionTest,
    IntegrationProvider,
    ProviderContext,
    TestStep,
)
from app.integrations.registry import get_provider, get_providers
from app.models.ai import RiskLevel
from app.models.integration import ConnectionStatus, ExternalItem, Integration, UserConnection
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.credential_vault import CredentialVault

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
        if scopes:
            from dataclasses import replace

            config = replace(config, scopes=tuple(scopes))
        redirect = (
            f"{self.settings.api_public_url.rstrip('/')}{self.settings.api_prefix}"
            f"/oauth/{provider.manifest.id}/callback"
        )
        return OAuthClient(config, redirect)

    async def start_oauth(
        self, user: User, provider_id: str, *, selected_scopes: list[str] | None
    ) -> str:
        provider = self.provider_or_404(provider_id)
        if provider.manifest.auth != AuthType.oauth2:
            raise ValidationFailed("This integration does not use OAuth.")
        scopes = provider.scopes_for(selected_scopes)
        conn = await self._get_or_create(user, provider)
        if conn.status == ConnectionStatus.disconnected or conn.status == ConnectionStatus.pending:
            conn.status = ConnectionStatus.connecting
        conn.scopes = scopes
        await self.db.commit()
        client = self._oauth_client(provider, scopes)
        return await client.begin(context={"user_id": str(user.id), "connection_id": str(conn.id)})

    async def complete_oauth(
        self,
        user: User,
        provider_id: str,
        *,
        code: str | None,
        state: str | None,
        error: str | None,
    ) -> UserConnection:
        provider = self.provider_or_404(provider_id)
        client = self._oauth_client(provider)
        record = await client.consume_state(state)
        ctx_info = record.get("context") or {}
        if ctx_info.get("user_id") != str(user.id):
            from app.core.exceptions import InvalidOAuthState

            raise InvalidOAuthState()
        conn = await self._get_or_create(user, provider)
        if error or not code:
            metrics.oauth_failures.labels(provider_id, "authorize").inc()
            await self._fail(
                conn,
                ProviderError(
                    ProviderErrorKind.auth_failed, error or "denied", provider=provider_id
                ),
                status=ConnectionStatus.error,
            )
            raise ProviderError(ProviderErrorKind.auth_failed, provider=provider_id).as_api_error()
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
        await self._finish_connect(user, provider, conn)
        return conn

    async def refresh_if_needed(self, user: User, conn: UserConnection) -> None:
        """Refresh an OAuth token nearing expiry. Marks the connection expired if that fails."""
        if conn.auth_type != AuthType.oauth2.value or conn.token_expires_at is None:
            return
        if conn.token_expires_at - utcnow() > REFRESH_LEEWAY:
            return
        provider = self.provider_or_404(conn.provider)
        try:
            tokens = await provider.refresh_credentials(self.context(user, conn))
        except ProviderError as exc:
            await self._fail(conn, exc)
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

    # --- token / config connect -------------------------------------------------------------------

    async def connect_with_config(
        self, user: User, provider_id: str, *, config: dict[str, Any], token: str | None
    ) -> UserConnection:
        provider = self.provider_or_404(provider_id)
        manifest = provider.manifest
        token_spec = manifest.token_auth
        uses_token = manifest.auth == AuthType.token or (
            manifest.auth == AuthType.oauth2 and token_spec is not None
        )
        if manifest.auth == AuthType.oauth2 and token_spec is None:
            raise ValidationFailed("This integration connects with OAuth. Use the connect button.")
        fields = list(token_spec.fields) if token_spec is not None else list(manifest.config_fields)
        errors: dict[str, list[str]] = {
            f.key: ["Required"]
            for f in fields
            if f.required and f.kind != "secret" and not str(config.get(f.key, "")).strip()
        }
        if uses_token and not (token or "").strip():
            errors["token"] = ["Required"]
        if errors:
            raise ValidationFailed("Some settings are missing.", details={"fields": errors})
        conn = await self._get_or_create(user, provider)
        allowed = {f.key for f in fields if f.kind != "secret"}
        conn.config = {k: str(v).strip() for k, v in config.items() if k in allowed}
        conn.status = ConnectionStatus.connecting
        conn.auth_type = AuthType.token.value if uses_token else manifest.auth.value
        if uses_token:
            self.vault.store_token(conn, (token or "").strip())
            conn.token_expires_at = None
            # A personal token carries whatever the user granted it; we can't enumerate scopes.
            conn.scopes = [p.scope for p in manifest.permissions]
        await self.db.flush()
        await self._finish_connect(user, provider, conn)
        return conn

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
        provider = self.provider_or_404(conn.provider)
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
            provider = get_provider(conn.provider)
            if provider is None:
                continue
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
