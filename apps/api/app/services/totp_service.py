from __future__ import annotations

import base64, hashlib, hmac, secrets, struct, urllib.parse, uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt, encrypt
from app.core.exceptions import Unauthorized, ValidationFailed
from app.db.base import utcnow
from app.models.user import User

STEP = 30

def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")

def valid(secret: str, code: str, *, drift: int = 1) -> bool:
    if not code.isdigit() or len(code) != 6: return False
    now = int(utcnow().timestamp() // STEP)
    for counter in range(now - drift, now + drift + 1):
        digest = hmac.new(base64.b32decode(secret + "=" * (-len(secret) % 8)), struct.pack(">Q", counter), hashlib.sha1).digest()
        offset = digest[-1] & 15; token = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7fffffff) % 1_000_000
        if hmac.compare_digest(f"{token:06d}", code): return True
    return False

def uri(secret: str, email: str) -> str:
    label = urllib.parse.quote(f"Notely AI:{email}")
    return f"otpauth://totp/{label}?secret={secret}&issuer=Notely%20AI&algorithm=SHA1&digits=6&period=30"

class TOTPService:
    def __init__(self, db: AsyncSession) -> None: self.db = db
    async def begin(self, user: User) -> tuple[str, str]:
        secret = new_secret(); user.totp_pending_secret_encrypted = encrypt(secret); user.totp_pending_expires_at = utcnow() + timedelta(minutes=10)
        await self.db.commit(); return secret, uri(secret, user.email)
    async def confirm(self, user: User, code: str) -> list[str]:
        if not user.totp_pending_secret_encrypted or not user.totp_pending_expires_at or user.totp_pending_expires_at < utcnow(): raise ValidationFailed("Your setup code expired. Start again.", code="TOTP_SETUP_EXPIRED")
        secret = decrypt(user.totp_pending_secret_encrypted)
        if not valid(secret, code): raise ValidationFailed("That authenticator code is not valid.", code="INVALID_TOTP")
        user.totp_secret_encrypted = encrypt(secret); user.totp_pending_secret_encrypted = None; user.totp_pending_expires_at = None
        codes = [secrets.token_urlsafe(8).upper() for _ in range(10)]
        prefs = dict(user.preferences or {}); prefs["recovery_code_hashes"] = [hashlib.sha256(c.encode()).hexdigest() for c in codes]; user.preferences = prefs
        await self.db.commit(); return codes
    async def verify(self, user: User, code: str) -> bool:
        if not user.totp_secret_encrypted: return False
        return valid(decrypt(user.totp_secret_encrypted), code)
    async def use_recovery_code(self, user: User, code: str) -> bool:
        digest = hashlib.sha256(code.strip().upper().encode()).hexdigest(); prefs = dict(user.preferences or {}); codes = list(prefs.get("recovery_code_hashes") or [])
        if digest not in codes: return False
        codes.remove(digest); prefs["recovery_code_hashes"] = codes; user.preferences = prefs; await self.db.commit(); return True
    async def disable(self, user: User) -> None:
        user.totp_secret_encrypted = None; user.totp_pending_secret_encrypted = None; user.totp_pending_expires_at = None
        prefs = dict(user.preferences or {}); prefs.pop("recovery_code_hashes", None); user.preferences = prefs; await self.db.commit()
