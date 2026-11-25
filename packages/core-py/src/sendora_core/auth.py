"""Owner login: argon2 password hashes and signed session tokens. Single tenant, roles owner, approver and viewer (read only)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_ph = PasswordHasher()
ROLES = ("owner", "approver", "viewer")
WRITE_ROLES = ("owner", "approver")  # may change data and decide approvals
READ_ROLES = ROLES  # every signed in role may read


def can_read(role: str) -> bool:
    return role in READ_ROLES


def can_write(role: str) -> bool:
    """The viewer role is read only. Owner and approver may write."""
    return role in WRITE_ROLES


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


_dummy_hash: str | None = None


def verify_password_or_dummy(password: str, hashed: str | None) -> bool:
    """Like verify_password, but when there is no account (hashed is None) it still does the same amount of work against a throw away hash,
    so the answer time does not tell a stranger which email addresses are accounts. Always False for a missing account."""
    global _dummy_hash
    if hashed is None:
        if _dummy_hash is None:
            _dummy_hash = _ph.hash("not-a-real-account-password")
        verify_password(password, _dummy_hash)
        return False
    return verify_password(password, hashed)


def clean_email(raw: str) -> str:
    """One spelling per address (trimmed, lower case, at most 254 characters), used for the account lookup AND the throttle key,
    so adding spaces or capitals never gives an attacker a fresh set of tries."""
    return (raw or "").strip().lower()[:254]


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_session_token(secret: str, user: str, role: str, ttl_s: int = 8 * 3600, now: float | None = None) -> str:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    body = _b64(json.dumps({"u": user, "r": role, "exp": int((now or time.time()) + ttl_s)}).encode())
    sig = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_session_token(secret: str, token: str, now: float | None = None) -> dict | None:
    """Return {'user', 'role'} for a valid unexpired token, otherwise None."""
    try:
        body, sig = token.split(".", 1)
        good = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig.encode(), good.encode()):
            return None
        data = json.loads(_unb64(body))
        if data["exp"] < (now or time.time()) or data["r"] not in ROLES:
            return None
        return {"user": data["u"], "role": data["r"]}
    except (ValueError, KeyError, TypeError, AttributeError, json.JSONDecodeError):
        return None


def verify_webhook_signature(secret: str, body: bytes, signature_hex: str) -> bool:
    """Generic HMAC SHA256 webhook check with constant time compare. Vendor specific schemes live in adapters."""
    good = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(good.encode(), (signature_hex or "").lower().encode())
