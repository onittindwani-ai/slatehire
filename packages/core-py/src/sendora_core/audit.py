"""Append only audit log with a hash chain, so edits or deletions are detectable."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from sendora_core.db import utcnow
from sendora_core.models import AuditEntry

GENESIS = "0" * 64


def _digest(prev: str, actor: str, action: str, target: str | None, detail: dict, created_at: str) -> str:
    body = json.dumps([prev, actor, action, target, detail, created_at], sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def record_audit(session: Session, actor: str, action: str, target: str | None = None, detail: dict | None = None) -> AuditEntry:
    detail = detail or {}
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(727001)"))  # one writer at a time, so the chain cannot fork
    last = session.scalars(select(AuditEntry).order_by(AuditEntry.id.desc()).limit(1)).first()
    prev = last.entry_hash if last else GENESIS
    created = utcnow().isoformat()
    entry = AuditEntry(
        actor=actor, action=action, target=target, detail=detail, prev_hash=prev,
        entry_hash=_digest(prev, actor, action, target, detail, created), created_at=created,
    )
    session.add(entry)
    session.flush()
    return entry


def verify_audit_chain(session: Session) -> tuple[bool, int | None]:
    """Return (ok, first_bad_id). ok is True when every link matches."""
    prev = GENESIS
    for e in session.scalars(select(AuditEntry).order_by(AuditEntry.id)):
        if e.prev_hash != prev or e.entry_hash != _digest(prev, e.actor, e.action, e.target, e.detail, e.created_at):
            return False, e.id
        prev = e.entry_hash
    return True, None
