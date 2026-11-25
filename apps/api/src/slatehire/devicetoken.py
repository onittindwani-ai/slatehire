"""A signed note that this browser has signed in as this account before. The sign in limits use it so the owner is never shut out by someone else's bad tries.

Why it exists: when every visitor reaches the API as the same address (a proxy whose forwarded address is not trusted, or a CDN in front of the proxy), the per address limits
are shared by everyone, and one bad try every 10 seconds at the owner's email keeps the owner out. A browser that already signed in carries this token, and the limits then
count that browser on its own instead of the shared address.

Safety: it is made only after a password was verified, it names the account (as a hash, never the address), it is signed with a key derived from SESSION_SECRET that is not the
session key (so it can never be read as a session), it expires, and the web app keeps it in an httpOnly cookie. It proves nothing about the password and never signs anyone in.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

DEVICE_TTL_S = 30 * 24 * 3600


def _key(secret: str) -> bytes:
    return hashlib.sha256(b"slatehire-device-v1|" + secret.encode()).digest()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _account(email: str) -> str:
    return hashlib.sha256(email.encode()).hexdigest()[:20]


def make(secret: str, email: str, device_id: str | None = None, now: float | None = None) -> str:
    """A fresh note for this account. Pass the id of the browser's earlier note to keep one id (and one bucket) per browser."""
    body = _b64(json.dumps({"a": _account(email), "d": device_id or secrets.token_hex(8), "exp": int((now or time.time()) + DEVICE_TTL_S)}, separators=(",", ":")).encode())
    return f"{body}.{_b64(hmac.new(_key(secret), body.encode(), hashlib.sha256).digest())}"


def read(secret: str, token: str | None, email: str, now: float | None = None) -> str | None:
    """The browser's id when the note is genuine, not expired and was made for this account, otherwise None."""
    if not token or len(token) > 400:
        return None
    try:
        body, sig = token.split(".", 1)
        good = _b64(hmac.new(_key(secret), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig.encode(), good.encode()):
            return None
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if data["exp"] < (now or time.time()) or data["a"] != _account(email) or not isinstance(data["d"], str) or len(data["d"]) > 32:
            return None
        return data["d"]
    except (ValueError, KeyError, TypeError, AttributeError, UnicodeError):
        return None
