"""Federated sign-in providers for Notely accounts (not integration providers).

A provider is enabled only when its client id and secret are configured. The registry is the
one place that knows provider endpoints; the auth router is provider-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.core.exceptions import ProviderNotConfigured
from app.core.oauth import OAuthClient, OAuthClientConfig, OAuthEndpoints
from app.models.user import SignInProvider


@dataclass(frozen=True)
class ProfileClaims:
    subject: str
    email: str | None
    email_verified: bool
    display_name: str | None
    avatar_url: str | None


@dataclass(frozen=True)
class SignInProviderSpec:
    id: SignInProvider
    display_name: str
    config: OAuthClientConfig


def _google(settings: Settings) -> SignInProviderSpec | None:
    if not (settings.oauth_google_client_id and settings.oauth_google_client_secret):
        return None
    return SignInProviderSpec(
        id=SignInProvider.google,
        display_name="Google",
        config=OAuthClientConfig(
            provider_id="signin-google",
            client_id=settings.oauth_google_client_id,
            client_secret=settings.oauth_google_client_secret,
            scopes=("openid", "email", "profile"),
            endpoints=OAuthEndpoints(
                authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
                token_url="https://oauth2.googleapis.com/token",
                jwks_url="https://www.googleapis.com/oauth2/v3/certs",
                issuer="https://accounts.google.com",
                extra_authorize_params={"prompt": "select_account"},
            ),
        ),
    )


def _microsoft(settings: Settings) -> SignInProviderSpec | None:
    if not (settings.oauth_microsoft_client_id and settings.oauth_microsoft_client_secret):
        return None
    tenant = settings.oauth_microsoft_tenant
    return SignInProviderSpec(
        id=SignInProvider.microsoft,
        display_name="Microsoft",
        config=OAuthClientConfig(
            provider_id="signin-microsoft",
            client_id=settings.oauth_microsoft_client_id,
            client_secret=settings.oauth_microsoft_client_secret,
            scopes=("openid", "email", "profile"),
            endpoints=OAuthEndpoints(
                authorize_url=f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
                token_url=f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                jwks_url=f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
                # Multi-tenant apps ("common") receive tenant-specific issuers; skip issuer pinning.
                issuer=None
                if tenant in ("common", "organizations", "consumers")
                else f"https://login.microsoftonline.com/{tenant}/v2.0",
                userinfo_url="https://graph.microsoft.com/oidc/userinfo",
            ),
        ),
    )


def enabled_sign_in_providers(settings: Settings) -> list[SignInProviderSpec]:
    return [spec for spec in (_google(settings), _microsoft(settings)) if spec is not None]


def get_sign_in_provider(settings: Settings, provider_id: str) -> SignInProviderSpec:
    for spec in enabled_sign_in_providers(settings):
        if spec.id.value == provider_id:
            return spec
    raise ProviderNotConfigured()


def redirect_uri_for(settings: Settings, provider_id: str) -> str:
    base = settings.api_public_url.rstrip("/")
    return f"{base}{settings.api_prefix}/auth/oauth/{provider_id}/callback"


def build_client(settings: Settings, spec: SignInProviderSpec) -> OAuthClient:
    return OAuthClient(spec.config, redirect_uri_for(settings, spec.id.value))


def claims_to_profile(claims: dict[str, Any], userinfo: dict[str, Any]) -> ProfileClaims:
    merged = {**userinfo, **claims}
    email = merged.get("email") or merged.get("preferred_username")
    verified_raw = merged.get("email_verified", False)
    verified = verified_raw is True or str(verified_raw).lower() == "true"
    return ProfileClaims(
        subject=str(merged["sub"]),
        email=email.lower() if isinstance(email, str) else None,
        email_verified=verified,
        display_name=merged.get("name") or merged.get("given_name"),
        avatar_url=merged.get("picture"),
    )
