# ADR-0003: One OAuth/OIDC client for sign-in and integrations

**Status:** Accepted · 2026-09-19

## Context

The PRD requires PKCE, random state, state validation, redirect-URI validation and encrypted
token storage for every provider, and forbids duplicated OAuth handling.

## Decision

`app/core/oauth.py` is the only authorization-code implementation. It is configured with
endpoint data (`OAuthEndpoints`) and credentials (`OAuthClientConfig`) and knows nothing about
any specific vendor. State + PKCE verifier + redirect URI are stored server-side (Redis via `KV`)
for 10 minutes and consumed exactly once. Redirect URIs are derived from `API_PUBLIC_URL`.

Sign-in providers (Google, Microsoft) live in `app/services/sign_in_providers.py`. Integration
providers (Slack, Notion, …) will supply their own `OAuthClientConfig` from their adapter and
reuse the same client; tokens they receive are encrypted with `app/core/crypto.py` before storage.

## Consequences

- Provider adapters are configuration + API mapping, not OAuth re-implementations.
- OAuth tests exercise the client once; provider tests only check configuration.
- Non-OAuth auth styles (API keys, personal tokens) are handled by the provider contract's
  `auth` field and do not go through this client.
