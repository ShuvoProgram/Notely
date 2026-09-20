"""Shared Google OAuth plumbing for Gmail, Google Calendar and Google Drive.

All three use the same Google Cloud OAuth client (OAUTH_GOOGLE_CLIENT_ID/SECRET — the one also
used for Google sign-in) with different scopes; each is its own connection so users grant only
what they want."""

from __future__ import annotations

from typing import Any

from app.core.oauth import OAuthEndpoints
from app.integrations.base.provider import ConnectionIdentity, ProviderContext
from app.integrations.base.rest import RestOAuthProvider

GOOGLE_ENDPOINTS = OAuthEndpoints(
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    # offline + consent → a refresh token on every connect, so connections survive the 1h token.
    extra_authorize_params={
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    },
)


class GoogleProvider(RestOAuthProvider):
    settings_prefix = "google"
    endpoints = GOOGLE_ENDPOINTS
    use_pkce = True

    async def identity(self, ctx: ProviderContext) -> ConnectionIdentity:
        """Who we're connected as. Each product reads it from its own API, because the
        userinfo endpoint needs the `email`/`profile` scopes that a Gmail/Calendar/Drive token
        was deliberately not granted."""
        email = await self.account_email(ctx)
        return ConnectionIdentity(
            external_account_id=email,
            external_account_name=email,
            metadata={"email": email},
        )

    async def account_email(self, ctx: ProviderContext) -> str:
        raise NotImplementedError

    @staticmethod
    def items(body: dict[str, Any], key: str) -> list[dict[str, Any]]:
        value = body.get(key)
        return value if isinstance(value, list) else []
