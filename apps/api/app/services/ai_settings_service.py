"""Per-user model configuration (bring your own key). The key is encrypted with the same
Fernet key as provider tokens; it is decrypted only to build a model client."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.byo import (
    PROVIDER_CATALOG,
    BYOModel,
    BYOProvider,
    ModelTest,
    classify_error,
    key_hint,
    list_models,
    normalise_base_url,
    provider_info,
    test_model,
)
from app.core import crypto
from app.core.config import Settings
from app.core.exceptions import ValidationFailed
from app.db.base import utcnow
from app.models.ai import UserAISetting
from app.models.user import User


class AISettingsService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def _key(self) -> str:
        if not self.settings.encryption_key:
            raise ValidationFailed(
                "This deployment has no ENCRYPTION_KEY, so API keys can't be stored safely.",
                code="ENCRYPTION_NOT_CONFIGURED",
            )
        return self.settings.encryption_key

    async def get(self, user: User) -> UserAISetting | None:
        return await self.db.scalar(select(UserAISetting).where(UserAISetting.user_id == user.id))

    async def resolve(self, user: User) -> BYOModel | None:
        """The user's model to run with, or None to use the workspace gateway."""
        row = await self.get(user)
        if row is None or not row.enabled or not row.api_key_encrypted:
            return None
        return BYOModel(
            provider=BYOProvider(row.provider),
            model=row.model,
            api_key=crypto.decrypt(row.api_key_encrypted, key=self._key()),
            base_url=row.base_url,
        )

    async def upsert(
        self,
        user: User,
        *,
        provider: str,
        model: str,
        base_url: str | None,
        api_key: str | None,
        enabled: bool,
    ) -> UserAISetting:
        try:
            byo_provider = BYOProvider(provider)
        except ValueError as exc:
            raise ValidationFailed(
                "Unknown provider.", details={"fields": {"provider": ["Unknown provider"]}}
            ) from exc
        info = provider_info(byo_provider)
        model = model.strip()
        if not model:
            raise ValidationFailed(
                "Model is required.", details={"fields": {"model": ["Required"]}}
            )
        try:
            base = normalise_base_url(base_url)
        except ValueError as exc:
            raise ValidationFailed(str(exc), details={"fields": {"base_url": [str(exc)]}}) from exc
        if info.needs_base_url and not base:
            raise ValidationFailed(
                "Base URL is required for this provider.",
                details={"fields": {"base_url": ["Required"]}},
            )
        if not info.needs_base_url:
            base = None
        row = await self.get(user)
        if row is None:
            row = UserAISetting(tenant_id=user.tenant_id, user_id=user.id, provider=provider)
            self.db.add(row)
        changed_identity = row.provider != provider or row.model != model or row.base_url != base
        row.provider = provider
        row.model = model
        row.base_url = base
        row.enabled = enabled
        key = (api_key or "").strip()
        if key:
            row.api_key_encrypted = crypto.encrypt(key, key=self._key())
            row.key_hint = key_hint(key)
            changed_identity = True
        elif not row.api_key_encrypted and byo_provider != BYOProvider.openai_compatible:
            raise ValidationFailed(
                "An API key is required.", details={"fields": {"api_key": ["Required"]}}
            )
        elif not row.api_key_encrypted:
            # Local OpenAI-compatible servers usually need no key; store a placeholder.
            row.api_key_encrypted = crypto.encrypt("not-needed", key=self._key())
            row.key_hint = ""
        if changed_identity:
            row.verified_at = None
            row.last_error = None
        await self.db.commit()
        return row

    async def test(self, user: User) -> ModelTest:
        row = await self.get(user)
        config = await self.resolve(user) if row and row.api_key_encrypted else None
        if row is None or config is None:
            raise ValidationFailed("Save a provider, model and API key first.")
        result = await test_model(config)
        row.verified_at = utcnow() if result.ok else None
        row.last_error = None if result.ok else result.detail
        await self.db.commit()
        return result

    async def list_models(
        self, user: User, *, provider: str, api_key: str | None, base_url: str | None
    ) -> list[str]:
        """Models available to a key: the one being typed, or the stored one for that provider."""
        try:
            provider_id = BYOProvider(provider)
        except ValueError as exc:
            raise ValidationFailed("Unknown provider.") from exc
        key = (api_key or "").strip()
        if not key:
            row = await self.get(user)
            if row is not None and row.provider == provider and row.api_key_encrypted:
                key = crypto.decrypt(row.api_key_encrypted, key=self._key())
                base_url = base_url or row.base_url
        if not key and provider_id != BYOProvider.openai_compatible:
            raise ValidationFailed(
                "Enter an API key first.", details={"fields": {"api_key": ["Required"]}}
            )
        try:
            base = normalise_base_url(base_url) or provider_info(provider_id).default_base_url
        except ValueError as exc:
            raise ValidationFailed(str(exc), details={"fields": {"base_url": [str(exc)]}}) from exc
        config = BYOModel(provider=provider_id, model="", api_key=key, base_url=base)
        try:
            return await list_models(config)
        except Exception as exc:  # noqa: BLE001 — same classification as the test button
            raise ValidationFailed(classify_error(exc), code="MODEL_LIST_FAILED") from exc

    async def delete(self, user: User) -> None:
        row = await self.get(user)
        if row is not None:
            await self.db.delete(row)
            await self.db.commit()

    @staticmethod
    def catalog() -> list[dict[str, Any]]:
        from app.ai.byo import as_dict

        return [as_dict(p) for p in PROVIDER_CATALOG]
