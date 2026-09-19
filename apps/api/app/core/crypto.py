"""Symmetric encryption at rest for provider credentials (Fernet: AES-128-CBC + HMAC-SHA256).

The key comes from ENCRYPTION_KEY; generate one with `python -m app.core.crypto`.
Encrypted values are stored as opaque strings and never leave the API.
"""

from __future__ import annotations

import base64
import sys

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class EncryptionError(RuntimeError):
    pass


def generate_key() -> str:
    return Fernet.generate_key().decode()


def is_valid_key(key: str) -> bool:
    try:
        return len(base64.urlsafe_b64decode(key.encode())) == 32
    except Exception:
        return False


def _fernet(key: str | None = None) -> Fernet:
    raw = key or get_settings().encryption_key
    if not raw:
        raise EncryptionError("ENCRYPTION_KEY is not configured")
    if not is_valid_key(raw):
        raise EncryptionError("ENCRYPTION_KEY is not a valid Fernet key")
    return Fernet(raw.encode())


def encrypt(plaintext: str, *, key: str | None = None) -> str:
    return _fernet(key).encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str, *, key: str | None = None) -> str:
    try:
        return _fernet(key).decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionError("Ciphertext could not be decrypted with the configured key") from exc


if __name__ == "__main__":
    sys.stdout.write(generate_key() + "\n")
