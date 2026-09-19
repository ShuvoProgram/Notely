# ADR-0001: Opaque server-side sessions instead of JWTs

**Status:** Accepted · 2026-09-19

## Context

Notely needs first-party authentication with immediate revocation (sign out other devices,
password change ends sessions) and must never expose credentials to browser JavaScript.

## Decision

Sessions are opaque 256-bit random tokens delivered in an `HttpOnly; SameSite=Lax` cookie.
The database stores `HMAC-SHA256(SESSION_SECRET, token)` plus metadata (user agent, IP, expiry,
revocation). Every request resolves the session with one indexed lookup; expiry slides.

## Consequences

- Revocation is instant and auditable; no token blacklist is needed.
- A database leak alone cannot forge sessions (the HMAC key lives in the environment).
- One database read per authenticated request. Acceptable at MVP scale; a Redis session cache
  can be added behind `AuthService.resolve_session` without changing callers.
- Stateless JWT access tokens are not used for the browser. If a public API needs bearer tokens
  later they will be a separate, scoped credential type.
