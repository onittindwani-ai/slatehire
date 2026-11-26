"""Erasure that lasts. When a person is deleted their application is gone, so the same address coming in again (a mailbox that still holds the message, an ATS pull, a webhook
retry) would add them back as a stranger. A deleted person leaves one thing behind: a keyed one way hash of their address (and of the outside reference they arrived under), with
the date. It holds nothing readable and it blocks the same address and the same reference from being added again, until the owner lifts it on purpose.

The key is SUPPRESSION_KEY, from the environment. It is never stored in the database or in a backup of it, so someone who holds a dump cannot test whether a known address was erased.
Hashes made before the key existed (scheme "salt", with a salt that sat in the database) are still checked, and are still lifted.

What an address match covers: capitals, spaces, a plus tag (ann+jobs@x is ann@x), full width characters, and punctuation stuck to the end of the address. It does not cover a different
address of the same person, a Gmail address with dots moved, or a person who writes with a new address and a new message: nobody can be recognised by anything that is not stored.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
import unicodedata
from pathlib import Path

from sqlalchemy import delete, event, func, select
from sqlalchemy.orm import Session

from slatehire.models import State, Suppression
from sendora_core.audit import record_audit
from sendora_core.auth import clean_email

SALT_KEY = "suppression_salt"
ERASED_LIST = "erased-hashes.txt"  # one line per kept hash, appended in the export folder: kept and restored with the exports, and re applied after a restore (see reapply.py)
# A line is `digest kind group time`, and a lifted hash adds one more line of the same shape ending in `lift`. The time (nanoseconds, the real clock) says which line is newest for a digest, and the
# newest line wins, so erasing, lifting and erasing again can be replayed in any order. A line without a time (older lists) is the oldest. A group that is not known is written as `-`.
_TRIM = " \t\r\n.,;:!?)>]}'\"<([{"


def normalize_email(email: str) -> str:
    """One spelling for one address: full width characters folded, capitals and spaces gone, punctuation at either end taken off, and the plus tag cut out of the part before the @."""
    e = clean_email(unicodedata.normalize("NFKC", email or "")).strip(_TRIM)
    if "@" not in e:
        return ""
    local, _, domain = e.rpartition("@")
    local = local.split("+", 1)[0]
    domain = domain.strip(_TRIM + "/")
    return f"{local}@{domain}" if local and "." in domain else ""


def _legacy_salt(s: Session, create: bool = False) -> bytes | None:
    row = s.get(State, SALT_KEY)
    if row is None or not row.value:
        if not create:
            return None
        if row is None:
            row = State(key=SALT_KEY, value=secrets.token_hex(24))
            s.add(row)
        else:
            row.value = secrets.token_hex(24)
        s.flush()
    return row.value.encode()


def _key_of(s: Session) -> bytes | None:
    key = (s.info.get("suppression_key") or "").strip()
    return key.encode() if key else None


def _mac(secret: bytes, kind: str, value: str) -> str:
    return hmac.new(secret, f"{kind}:{value}".encode("utf-8", "replace"), hashlib.sha256).hexdigest()


def _forms(s: Session, email: str, source: str, ref: str | None) -> list[tuple[str, str, str]]:
    """(kind, digest, scheme) for everything that identifies this person: under the key when there is one, and under the old database salt when rows made with it may exist."""
    out: list[tuple[str, str, str]] = []
    values: list[tuple[str, str]] = []
    if normalize_email(email):
        values.append(("email", normalize_email(email)))
    if ref:
        values.append(("ref", f"{(source or '').lower()}|{ref}"))
    key, legacy = _key_of(s), _legacy_salt(s, create=_key_of(s) is None)
    for kind, value in values:
        if key is not None:
            out.append((kind, _mac(key, kind, value), "key"))
        if legacy is not None:
            out.append((kind, _mac(legacy, kind, value), "salt"))
            if kind == "email" and clean_email(email) and clean_email(email) != value:
                out.append((kind, _mac(legacy, kind, clean_email(email)), "salt"))  # how the first release spelled it
    return out


def record(s: Session, email: str, source: str, ref: str | None, now) -> int:
    """Remember an erased person. Returns how many hashes are kept for them afterwards (0 when there was nothing to hash, for example a person with no address and no outside reference).
    The count is of hashes that exist, not only new ones, so erasing a second application of the same person says the truth."""
    forms = [f for f in _forms(s, email, source, ref) if f[2] == ("key" if _key_of(s) else "salt")]
    group = secrets.token_hex(8)
    fresh: list[tuple[str, str]] = []
    for kind, d, scheme in forms:
        row = s.scalars(select(Suppression).where(Suppression.digest == d)).first()
        if row is None:
            s.add(Suppression(digest=d, kind=kind, scheme=scheme, group_id=group, created_at=now))
            fresh.append((d, kind))
        elif not row.group_id:
            row.group_id = group
    s.flush()
    if fresh and _key_of(s):
        _append_after_commit(s, [(d, k, group, False) for d, k in fresh])
    return len(forms)


def _append_after_commit(s: Session, lines: list[tuple[str, str, str, bool]]) -> None:
    """Add the lines (hash, kind, group, lifted) to the erased list in the export folder once the change is saved for good (a rolled back deletion must not leave a line that would delete the
    person later, and a rolled back lift must not leave a line that would let them back). Each line carries the time it was written, so the order of the file does not matter."""
    folder = s.info.get("export_dir")
    if not folder or not lines:
        return
    at = time.time_ns()

    def write(_session) -> None:
        path = Path(folder) / ERASED_LIST
        path.parent.mkdir(parents=True, exist_ok=True)
        fresh = not path.exists()
        with path.open("a", encoding="utf-8") as fh:
            fh.writelines(f"{d} {kind} {group or '-'} {at + i}{' lift' if lifted else ''}\n" for i, (d, kind, group, lifted) in enumerate(lines))
        if fresh:
            path.chmod(0o600)

    event.listen(s, "after_commit", write, once=True)


def is_suppressed(s: Session, email: str, source: str, ref: str | None) -> bool:
    ds = [d for _k, d, _sc in _forms(s, email, source, ref)]
    return bool(ds) and s.scalars(select(Suppression.id).where(Suppression.digest.in_(ds)).limit(1)).first() is not None


def lift(s: Session, email: str, actor: str, source: str = "", reference: str | None = None) -> int:
    """The owner lets one person apply again (the person applied again on purpose), by address, by outside reference, or both. Returns how many hashes were removed. Everything kept from the
    same erasure goes with it, so lifting the address also lifts the webhook or ATS reference the person arrived under (and the other way round). Older hashes have no group: only the
    one that matches is removed."""
    forms = _forms(s, email, source, reference)
    ds = [d for _k, d, _sc in forms]
    removed = 0
    if ds:
        rows = list(s.scalars(select(Suppression).where(Suppression.digest.in_(ds))))
        groups = {r.group_id for r in rows if r.group_id}
        ids = {r.id for r in rows}
        if groups:
            ids |= set(s.scalars(select(Suppression.id).where(Suppression.group_id.in_(groups))))
        if ids:
            gone = list(s.scalars(select(Suppression).where(Suppression.id.in_(ids))))
            removed = int(s.execute(delete(Suppression).where(Suppression.id.in_(ids))).rowcount or 0)
            if _key_of(s):  # the list is written too, so that applying it after a restore does not delete the person who was let back in on purpose
                _append_after_commit(s, [(r.digest, r.kind, r.group_id or "", True) for r in gone if r.scheme == "key"])
    record_audit(s, actor, "suppression.lifted", None, {"removed": removed})
    return removed


def count(s: Session) -> int:
    return int(s.scalar(select(func.count()).select_from(Suppression)) or 0)


def digests_of(s: Session, email: str, source: str, ref: str | None) -> set[str]:
    """The keyed hashes of a person, used to match a live person against the erased list after a restore."""
    return {d for _k, d, scheme in _forms(s, email, source, ref) if scheme == "key"}
