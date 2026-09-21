"""Per-user model configuration (bring your own key). The key is encrypted with the same
Fernet key as provider tokens; it is decrypted only to build a model client.

Saving is verify-then-write: the draft is tested against the vendor first, and the stored,
working configuration is only replaced once the new one has answered. A key that arrives in
a request is used for that request and then either encrypted or forgotten — it is never
logged, echoed in an error, or returned by any endpoint."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.byo import (
    CATALOG,
    BYOModel,
    BYOProvider,
    ModelSpec,
    ModelTest,
    classify_error,
    key_hint,
    list_models,
    normalise_base_url,
    provider_spec,
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

    # --- drafts -----------------------------------------------------------------------------

    async def _draft(
        self,
        user: User,
        *,
        provider: str,
        model: str,
        base_url: str | None,
        api_key: str | None,
    ) -> tuple[BYOModel, bool]:
        """Validate the fields and resolve the key: the one in the request, else the stored one
        for the same provider. Returns (config, key_is_new)."""
        try:
            byo_provider = BYOProvider(provider)
        except ValueError as exc:
            raise ValidationFailed(
                "Unknown provider.", details={"fields": {"provider": ["Unknown provider"]}}
            ) from exc
        spec = provider_spec(byo_provider)
        model = model.strip()
        if not model:
            raise ValidationFailed(
                "Model is required.", details={"fields": {"model": ["Required"]}}
            )
        if spec.base_url_fixed:
            base = spec.default_base_url
        else:
            try:
                base = normalise_base_url(base_url)
            except ValueError as exc:
                raise ValidationFailed(
                    str(exc), details={"fields": {"base_url": [str(exc)]}}
                ) from exc
            if spec.needs_base_url and not base:
                raise ValidationFailed(
                    "Base URL is required for this provider.",
                    details={"fields": {"base_url": ["Required"]}},
                )
            if not spec.needs_base_url:
                base = None
        key = (api_key or "").strip()
        key_is_new = bool(key)
        if not key:
            row = await self.get(user)
            if row is not None and row.provider == provider and row.api_key_encrypted:
                key = crypto.decrypt(row.api_key_encrypted, key=self._key())
        if not key and not spec.key_optional:
            raise ValidationFailed(
                "An API key is required.", details={"fields": {"api_key": ["Required"]}}
            )
        return BYOModel(provider=byo_provider, model=model, api_key=key, base_url=base), key_is_new

    async def test_draft(
        self,
        user: User,
        *,
        provider: str,
        model: str,
        base_url: str | None,
        api_key: str | None,
    ) -> ModelTest:
        """Try a configuration without storing anything."""
        config, _ = await self._draft(
            user, provider=provider, model=model, base_url=base_url, api_key=api_key
        )
        return await test_model(config)

    # --- persistence ------------------------------------------------------------------------

    async def upsert(
        self,
        user: User,
        *,
        provider: str,
        model: str,
        base_url: str | None,
        api_key: str | None,
        enabled: bool,
        verify: bool = True,
    ) -> UserAISetting:
        """Save the configuration. With `verify` (the default) the draft must answer first;
        the previously saved configuration is untouched until it does."""
        config, key_is_new = await self._draft(
            user, provider=provider, model=model, base_url=base_url, api_key=api_key
        )
        result: ModelTest | None = None
        if verify:
            result = await test_model(config)
            if not result.ok:
                raise ValidationFailed(
                    result.detail, code="MODEL_TEST_FAILED", details={"fields": {"model": []}}
                )
        row = await self.get(user)
        if row is None:
            row = UserAISetting(tenant_id=user.tenant_id, user_id=user.id, provider=provider)
            self.db.add(row)
        row.provider = config.provider.value
        row.model = config.model
        row.base_url = config.base_url
        row.enabled = enabled
        if key_is_new or not row.api_key_encrypted:
            row.api_key_encrypted = crypto.encrypt(config.api_key or "not-needed", key=self._key())
            row.key_hint = key_hint(config.api_key) if config.api_key else ""
        if result is not None:
            row.verified_at = utcnow()
            row.last_error = None
            row.supports_tools = result.supports_tools
        else:
            row.verified_at = None
            row.last_error = None
            row.supports_tools = None
        await self.db.commit()
        return row

    async def test(self, user: User) -> ModelTest:
        row = await self.get(user)
        config = await self.resolve(user) if row and row.api_key_encrypted else None
        if row is None:
            raise ValidationFailed("Save a provider, model and API key first.")
        if config is None:
            # Saved but switched off: still testable.
            config = BYOModel(
                provider=BYOProvider(row.provider),
                model=row.model,
                api_key=crypto.decrypt(row.api_key_encrypted or "", key=self._key()),
                base_url=row.base_url,
            )
        result = await test_model(config)
        row.verified_at = utcnow() if result.ok else None
        row.last_error = None if result.ok else result.detail
        if result.ok:
            row.supports_tools = result.supports_tools
        await self.db.commit()
        return result

    async def list_models(
        self, user: User, *, provider: str, api_key: str | None, base_url: str | None
    ) -> list[ModelSpec]:
        """Models available to a key: the one being typed, or the stored one for that provider."""
        try:
            provider_id = BYOProvider(provider)
        except ValueError as exc:
            raise ValidationFailed("Unknown provider.") from exc
        spec = provider_spec(provider_id)
        key = (api_key or "").strip()
        if not key:
            row = await self.get(user)
            if row is not None and row.provider == provider and row.api_key_encrypted:
                key = crypto.decrypt(row.api_key_encrypted, key=self._key())
                base_url = base_url or row.base_url
        if not key and not spec.key_optional and provider_id != BYOProvider.openrouter:
            raise ValidationFailed(
                "Enter an API key first.", details={"fields": {"api_key": ["Required"]}}
            )
        try:
            base = normalise_base_url(base_url) or spec.default_base_url
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

        return [as_dict(p) for p in CATALOG]
