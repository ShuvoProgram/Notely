# ADR-0002: CSRF protection via SameSite cookies + Origin enforcement

**Status:** Accepted · 2026-09-19

## Context

Cookie-authenticated JSON APIs are exposed to cross-site request forgery. Classic synchroniser
tokens add a round trip and per-form plumbing that a SPA gains little from.

## Decision

1. Session cookie is `SameSite=Lax`, so browsers omit it on cross-site POST/PUT/PATCH/DELETE.
2. `CSRFOriginMiddleware` rejects unsafe requests whose `Origin` is not in the allow-list, whose
   `Origin` is `null`, or whose `Sec-Fetch-Site` is `cross-site`. Modern browsers always send
   `Origin` on cross-site unsafe requests and `Sec-Fetch-Site` on all fetches.
3. The web app calls the API through a same-origin proxy (`/api/*` rewrite), so legitimate
   requests carry the frontend origin.

## Consequences

- No CSRF token handling in forms or the API client.
- The OAuth callback (top-level GET) is unaffected; GET routes never mutate state.
- Non-browser clients (curl, scripts) work without an `Origin` header because they cannot be
  driven by a victim's browser.
- If the API is ever served from a different site than the web app, `ALLOWED_ORIGINS` must list
  the web origin and the cookie may need `SameSite=None; Secure`.
