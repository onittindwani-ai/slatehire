"""Background jobs: read new application emails, score the applicants who are waiting, delete expired data, note overdue onboarding tasks.

A job never moves an application. It only brings people in and scores them, so a person always has the next decision.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from slatehire import ingest, intake, retention, scoring_service
from slatehire.context import Ctx, get_state, set_state
from slatehire.models import OnboardingTask, Role
from sendora_core.adapters import AdapterError
from sendora_core.events import record_event
from sendora_core.jobs import Handler

INTERVALS = {"mailbox": 300, "score": 300, "retention": 6 * 3600, "onboarding": 3600}


def _role_titles(s: Session) -> dict[str, str]:
    return {r.key: r.title for r in s.scalars(select(Role))}


def _add_email(s: Session, ctx: Ctx, raw: bytes, now) -> str:
    titles = _role_titles(s)
    try:
        a = ingest.from_email(raw, titles)
    except ingest.IngestError:
        return "rejected"
    role = s.scalars(select(Role).where(Role.key == a.role_key)).first() if a.role_key else None
    if role is None:
        return "rejected"
    _app, status = intake.add_applicant(s, a, role, "mailbox", now, settings=ctx.settings)
    return status


def job_mailbox(s: Session, ctx: Ctx) -> dict:
    now = ctx.now(s)
    got = {"added": 0, "duplicate": 0, "rejected": 0}
    if ctx.settings.mailbox_adapter == "seed":
        if not ctx.settings.demo_mode:
            return got
        files = sorted((Path(ctx.settings.seed_dir) / "seed" / "inbox").glob("*.eml"))
        i = int(get_state(s, "inbox_next", "0") or 0)
        if i < len(files):
            got[_add_email(s, ctx, files[i].read_bytes(), now)] += 1
            set_state(s, "inbox_next", str(i + 1))
        return got
    mb = ctx.adapter(s, "mailbox")
    try:
        for uid, raw in mb.fetch_new(limit=25):
            got[_add_email(s, ctx, raw, now)] += 1
            mb.mark_seen(uid)
    except AdapterError:
        got["error"] = 1  # type: ignore[assignment]
    return got


def job_score(s: Session, ctx: Ctx) -> dict:
    now, n, scorer = ctx.now(s), 0, ctx.scorer(s)
    for app in scoring_service.unscored(s):
        scoring_service.score_application(s, app, "scorer", now, scorer)
        n += 1
    return {"scored": n}


def job_retention(s: Session, ctx: Ctx) -> dict:
    return {"deleted": retention.sweep(s, ctx.now(s), ctx.settings.retention_days)}


def job_onboarding(s: Session, ctx: Ctx) -> dict:
    today = ctx.today(s)
    late = [t for t in s.scalars(select(OnboardingTask).where(OnboardingTask.done.is_(False))) if date.fromisoformat(t.due_on) < today]
    if late:
        record_event(s, "onboarding.overdue", None, None, {"tasks": len(late)})
    return {"overdue": len(late)}


JOBS = {"mailbox": job_mailbox, "score": job_score, "retention": job_retention, "onboarding": job_onboarding}


def make_handlers(ctx: Ctx) -> dict[str, Handler]:
    return {kind: (lambda session, payload, fn=fn: fn(session, ctx)) for kind, fn in JOBS.items()}


def schedule_due(session: Session, ctx: Ctx) -> int:
    from sendora_core.db import utcnow
    from sendora_core.jobs import enqueue
    from sendora_core.models import Job

    n, now = 0, utcnow()
    for kind, secs in INTERVALS.items():
        last = session.scalars(select(Job).where(Job.kind == kind).order_by(Job.id.desc())).first()
        if last is None or (last.status in {"done", "failed"} and last.finished_at is not None and (now - last.finished_at.replace(tzinfo=now.tzinfo)).total_seconds() >= secs):
            enqueue(session, kind)
            n += 1
    return n


def run_cycle(session: Session, ctx: Ctx) -> dict:
    out = {k: fn(session, ctx) for k, fn in JOBS.items()}
    record_event(session, "cycle.ran", None, None, {"new": out["mailbox"].get("added", 0), "scored": out["score"]["scored"]})
    return out
