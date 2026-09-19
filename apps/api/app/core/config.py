"""Application settings. All configuration comes from environment variables / .env."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    app_name: str = "Notely AI"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"

    # Persistence
    database_url: str = "postgresql+asyncpg://notely:notely@localhost:5432/notely"
    redis_url: str = "redis://localhost:6379/0"

    # Secrets. Both are mandatory in production; defaults exist only for local dev/test.
    session_secret: str = Field(default="dev-only-session-secret-change-me", min_length=16)
    encryption_key: str = ""  # urlsafe base64 32-byte Fernet key; see `python -m app.core.crypto`

    # Sessions & cookies
    session_cookie_name: str = "notely_session"
    session_ttl_seconds: int = 60 * 60 * 24 * 7  # 7 days, sliding
    session_cookie_secure: bool = False  # forced True in production
    session_cookie_domain: str | None = None

    # Web origins allowed to call the API with cookies (CORS + CSRF origin check)
    frontend_origin: str = "http://localhost:3000"
    # Comma-separated in the environment; NoDecode stops pydantic-settings expecting JSON.
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    # Public URL of this API, used to build OAuth redirect URIs
    api_public_url: str = "http://localhost:8000"

    # Rate limiting (per window)
    rate_limit_enabled: bool = True
    rate_limit_auth_per_minute: int = 10
    rate_limit_default_per_minute: int = 120

    # Sign-in providers (enabled only when both id and secret are set)
    oauth_google_client_id: str = ""
    oauth_google_client_secret: str = ""
    oauth_microsoft_client_id: str = ""
    oauth_microsoft_client_secret: str = ""
    oauth_microsoft_tenant: str = "common"

    # LLM gateway (used from Phase 3 onwards; validated in readiness when set)
    litellm_api_base: str = ""
    litellm_api_key: str = ""

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cookie_secure(self) -> bool:
        return True if self.is_production else self.session_cookie_secure

    def validate_for_runtime(self) -> list[str]:
        """Return a list of configuration problems that make the service not-ready."""
        problems: list[str] = []
        if self.is_production:
            if self.session_secret.startswith("dev-only"):
                problems.append("SESSION_SECRET is using the development default")
            if not self.encryption_key:
                problems.append("ENCRYPTION_KEY is not set")
            if self.debug:
                problems.append("DEBUG must be false in production")
        if self.encryption_key:
            from app.core.crypto import is_valid_key

            if not is_valid_key(self.encryption_key):
                problems.append("ENCRYPTION_KEY is not a valid Fernet key")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
