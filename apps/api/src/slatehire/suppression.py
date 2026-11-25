"""Erasure that lasts. When a person is deleted their application is gone, so the same address coming in again (a mailbox that still holds the message, an ATS pull, a webhook
retry) would add them back as a stranger. A deleted person leaves one thing behind: a salted one way hash of their address (and of the outside reference they arrived under),
with the date. It holds nothing readable and it blocks the same address and the same reference from being added again, until the owner lifts it on purpose."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from slatehire.models import State, Suppression
from sendora_core.audit import record_audit
from sendora_core.auth import clean_email

SALT_KEY = "suppression_salt"


def _salt(s: Session) -> bytes:
    row = s.get(State, SALT_KEY)
    if row is None:
        row = State(key=SALT_KEY, value=secrets.token_hex(24))
        s.add(row)
        s.flush()
    elif not row.value:
        row.value = secrets.token_hex(24)
        s.flush()
    return row.value.encode()


def digest(s: Session, kind: str, value: str) -> str:
    return hmac.new(_salt(s), f"{kind}:{value}".encode("utf-8", "replace"), hashlib.sha256).hexdigest()


def _keys(s: Session, email: str, source: str, ref: str | None) -> list[tuple[str, str]]:
    out = []
    if clean_email(email) and "@" in clean_email(email):
        out.append(("email", digest(s, "email", clean_email(email))))
    if ref:
        out.append(("ref", digest(s, "ref", f"{(source or '').lower()}|{ref}")))
    return out


def record(s: Session, email: str, source: str, ref: str | None, now) -> int:
    """Remember an erased person. Returns how many new hashes were stored (0 when there was nothing to hash, for example a person with no address and no outside reference)."""
    n = 0
    for kind, d in _keys(s, email, source, ref):
        if s.scalars(select(Suppression).where(Suppression.digest == d)).first() is None:
            s.add(Suppression(digest=d, kind=kind, created_at=now))
            n += 1
    s.flush()
    return n


def is_suppressed(s: Session, email: str, source: str, ref: str | None) -> bool:
    ds = [d for _k, d in _keys(s, email, source, ref)]
    return bool(ds) and s.scalars(select(Suppression.id).where(Suppression.digest.in_(ds)).limit(1)).first() is not None


def lift(s: Session, email: str, actor: str) -> int:
    """The owner lets one address apply again (the person applied again on purpose). Returns how many hashes were removed. Outside references cannot be looked up from an
    address, and a new message or a new ATS record has a new reference anyway."""
    d = digest(s, "email", clean_email(email)) if clean_email(email) else ""
    n = s.execute(delete(Suppression).where(Suppression.digest == d)).rowcount if d else 0
    record_audit(s, actor, "suppression.lifted", None, {"removed": int(n or 0)})
    return int(n or 0)


def count(s: Session) -> int:
    return int(s.scalar(select(func.count()).select_from(Suppression)) or 0)
