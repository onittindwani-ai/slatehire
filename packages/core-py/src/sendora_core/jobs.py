"""Postgres or SQLite backed job queue and one worker loop. No Redis."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from sendora_core.db import session_scope, utcnow
from sendora_core.models import Job

Handler = Callable[[Session, dict], dict | None]


def enqueue(session: Session, kind: str, payload: dict | None = None, delay_s: float = 0, max_attempts: int = 3) -> Job:
    job = Job(kind=kind, payload=payload or {}, max_attempts=max_attempts, run_at=utcnow() + timedelta(seconds=delay_s))
    session.add(job)
    session.flush()
    return job


def claim_next(session: Session) -> Job | None:
    """Atomically move one due job from queued to running. The conditional update makes double claims impossible."""
    now = utcnow()
    candidate = session.scalars(
        select(Job).where(Job.status == "queued", Job.run_at <= now).order_by(Job.run_at, Job.id).limit(1)
    ).first()
    if candidate is None:
        return None
    res = session.execute(
        update(Job).where(Job.id == candidate.id, Job.status == "queued").values(status="running", attempts=Job.attempts + 1)
    )
    session.flush()
    if res.rowcount != 1:
        return None
    session.refresh(candidate)
    return candidate


class Worker:
    def __init__(self, factory: sessionmaker[Session], handlers: dict[str, Handler], backoff_s: float = 30.0):
        self.factory, self.handlers, self.backoff_s = factory, handlers, backoff_s

    def run_once(self) -> bool:
        """Run one due job. Returns True when a job was handled (success or failure)."""
        with session_scope(self.factory) as s:
            job = claim_next(s)
            if job is None:
                return False
            job_id, kind, payload = job.id, job.kind, job.payload
        handler = self.handlers.get(kind)
        with session_scope(self.factory) as s:
            job = s.get(Job, job_id)
            try:
                if handler is None:
                    raise LookupError(f"No handler for job kind '{kind}'.")
                job.result = handler(s, payload) or {}
                job.status, job.finished_at = "done", utcnow()
            except Exception as exc:
                job.last_error = f"{type(exc).__name__}: {exc}"[:2000]
                if job.attempts >= job.max_attempts:
                    job.status, job.finished_at = "failed", utcnow()
                else:
                    job.status = "queued"
                    job.run_at = utcnow() + timedelta(seconds=self.backoff_s * 2 ** (job.attempts - 1))
        return True

    def drain(self, limit: int = 1000) -> int:
        n = 0
        while n < limit and self.run_once():
            n += 1
        return n
