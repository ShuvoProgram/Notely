"""Encrypt/decrypt provider credentials with the deployment ENCRYPTION_KEY (Fernet).

Tokens exist in plaintext only inside a request that needs them; the database, logs and API
responses only ever see ciphertext (or nothing)."""

from __future__ import annotations

from app.core import crypto
from app.core.config import Settings
from app.core.exceptions import APIError
from app.core.oauth import OAuthTokens
from app.integrations.base.provider import ProviderCredentials
from app.models.integration import UserConnection


class VaultUnavailable(APIError):
    status_code = 503
    code = "ENCRYPTION_KEY_MISSING"
    message = "Integrations are unavailable until ENCRYPTION_KEY is configured."


class CredentialVault:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _key(self) -> str:
        key = self.settings.encryption_key
        if not key or not crypto.is_valid_key(key):
            raise VaultUnavailable()
        return key

    def store_tokens(self, connection: UserConnection, tokens: OAuthTokens) -> None:
        key = self._key()
        connection.access_token_encrypted = crypto.encrypt(tokens.access_token, key=key)
        connection.refresh_token_encrypted = (
            crypto.encrypt(tokens.refresh_token, key=key) if tokens.refresh_token else None
        )

    def store_token(self, connection: UserConnection, token: str | None) -> None:
        connection.access_token_encrypted = (
            crypto.encrypt(token, key=self._key()) if token else None
        )
        connection.refresh_token_encrypted = None

    def load(self, connection: UserConnection) -> ProviderCredentials:
        if not connection.access_token_encrypted and not connection.refresh_token_encrypted:
            return ProviderCredentials()
        key = self._key()
        return ProviderCredentials(
            access_token=(
                crypto.decrypt(connection.access_token_encrypted, key=key)
                if connection.access_token_encrypted
                else None
            ),
            refresh_token=(
                crypto.decrypt(connection.refresh_token_encrypted, key=key)
                if connection.refresh_token_encrypted
                else None
            ),
        )

    @staticmethod
    def clear(connection: UserConnection) -> None:
        connection.access_token_encrypted = None
        connection.refresh_token_encrypted = None
        connection.token_expires_at = None
