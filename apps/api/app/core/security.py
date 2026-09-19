"""Password hashing and opaque session tokens."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from pwdlib import PasswordHash

_hasher = PasswordHash.recommended()  # argon2id


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password, password_hash)
    except Exception:
        return False


def new_session_token() -> str:
    """256-bit URL-safe random token. Only its keyed hash is persisted."""
    return secrets.token_urlsafe(32)


def hash_token(token: str, secret: str) -> str:
    """Keyed hash so a database leak alone cannot forge sessions."""
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()
