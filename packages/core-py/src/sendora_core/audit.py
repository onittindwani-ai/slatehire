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


def verify_audit_chain(session: Session, limit: int = 0) -> tuple[bool, int | None]:
    """Return (ok, first_bad_id). ok is True when every link matches.

    Rows are read in batches, so a log that has grown for years is never held in memory at once. `limit` 0 walks the whole log from the start.
    A positive `limit` walks only the newest `limit` rows and trusts the first one it reads as the starting point, so an edit older than that window is not seen."""
    batch_size = 500
    start = 0
    if limit > 0:
        start = session.scalars(select(AuditEntry.id).order_by(AuditEntry.id.desc()).offset(limit - 1).limit(1)).first() or 0
    prev: str | None = GENESIS if not start else None
    last_id = start - 1
    while True:
        batch = list(session.scalars(select(AuditEntry).where(AuditEntry.id > last_id, AuditEntry.id >= start).order_by(AuditEntry.id).limit(batch_size)))
        if not batch:
            return True, None
        for e in batch:
            if (prev is not None and e.prev_hash != prev) or e.entry_hash != _digest(e.prev_hash, e.actor, e.action, e.target, e.detail, e.created_at):
                return False, e.id
            prev = e.entry_hash
        last_id = batch[-1].id
        for e in batch:
            session.expunge(e)  # checked rows are not kept in memory; the caller's own objects stay
