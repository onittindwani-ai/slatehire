"""Background jobs: read new application emails, score the applicants who are waiting, delete expired data, note overdue onboarding tasks.

A job never moves an application. It only brings people in and scores them, so a person always has the next decision.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from slatehire import ingest, intake, retention, scoring_service
from slatehire.datadir import data_dir_or_none
from slatehire.context import Ctx, get_state, set_state
from slatehire.models import IntakeLog, OnboardingTask, Role
from sendora_core.adapters import AdapterError
from sendora_core.events import record_event
from sendora_core.jobs import Handler

log = logging.getLogger("slatehire.jobs")
INTERVALS = {"mailbox": 300, "score": 300, "retention": 6 * 3600, "onboarding": 3600}


def _role_titles(s: Session) -> dict[str, str]:
    return {r.key: r.title for r in s.scalars(select(Role))}


def _log_intake(s: Session, ref: str, status: str, why: str, now) -> None:
    s.add(IntakeLog(source="mailbox", ref=(ref or "unknown sender")[:160], status=status, detail=why[:300], created_at=now))


def _add_email(s: Session, ctx: Ctx, raw: bytes, now) -> tuple[str, str]:
    """Read one application email. Returns (status, why). A message that is not added says why, so a person can open the reason (the "Not added" list)."""
    titles = _role_titles(s)
    try:
        a = ingest.from_email(raw, titles, keep_unreadable=True)
    except ingest.IngestError as exc:
        return "rejected", str(exc)
    role = s.scalars(select(Role).where(Role.key == a.role_key)).first() if a.role_key else None
    if role is None and a.extra.get("role_ambiguous"):
        return "rejected", "The subject fits more than one role (" + ", ".join(a.extra["role_ambiguous"][:4]) + "). Add this person by hand under the right one, or ask them to write the exact role title."
    if role is None:
        return "rejected", "The subject does not name one of your roles. Write it as: Application for <role title>."
    _app, status = intake.add_applicant(s, a, role, "mailbox", now, settings=ctx.settings)
    return status, ""


def _handle_message(s: Session, ctx: Ctx, raw: bytes, now) -> str:
    """One message, on its own: whatever goes wrong inside it is rolled back alone, written to the "Not added" list by class name only (never by the
    applicant's words) and the rest of the batch goes on."""
    try:
        with s.begin_nested():
            status, why = _add_email(s, ctx, raw, now)
    except Exception as exc:  # noqa: BLE001 - one broken message must not stop the others
        log.warning("mailbox: one message was skipped (%s)", type(exc).__name__)
        status, why = "rejected", f"The message could not be stored ({type(exc).__name__})."
    if status == "rejected" and why:
        try:
            with s.begin_nested():
                _log_intake(s, ingest.sender_of(raw), "rejected", why, now)
        except Exception as exc:  # noqa: BLE001
            log.warning("mailbox: the skip could not be written to the list (%s)", type(exc).__name__)
    return status


def job_mailbox(s: Session, ctx: Ctx) -> dict:
    now = ctx.now(s)
    got = {"added": 0, "duplicate": 0, "rejected": 0}
    if ctx.settings.mailbox_adapter == "seed":
        if not ctx.settings.demo_shortcuts:
            return got
        folder = data_dir_or_none(ctx.settings.seed_dir)
        files = sorted((folder / "seed" / "inbox").glob("*.eml")) if folder else []
        i = int(get_state(s, "inbox_next", "0") or 0)
        if i < len(files):
            got[_handle_message(s, ctx, files[i].read_bytes(), now)] += 1
            set_state(s, "inbox_next", str(i + 1))
        return got
    mb = ctx.adapter(s, "mailbox")
    s.commit()  # let go of the write lock before the network: the mailbox can take seconds to answer
    try:
        messages = mb.fetch_new(limit=25)
    except AdapterError:
        got["error"] = 1  # type: ignore[assignment]
        return got
    handled: list[str] = []
    for uid, raw in messages:
        got[_handle_message(s, ctx, raw, now)] += 1
        handled.append(uid)
    limit = ctx.settings.imap_max_message_bytes
    for uid, sender, size in getattr(mb, "skipped", []):  # too large to download: said so in the Not added list, then marked read so it is not listed again every five minutes
        _log_intake(s, sender, "rejected", f"The message is {size / 1_000_000:.1f} MB, over the {limit / 1_000_000:.0f} MB limit (IMAP_MAX_MESSAGE_BYTES), so it was not downloaded. Ask the applicant for a smaller file, or add them by hand.", now)
        got["rejected"] += 1
        handled.append(uid)
    s.commit()  # the applicants are stored for good BEFORE any message is marked read: a failed save loses nothing
    try:
        mb.mark_seen_many(handled)
    except AdapterError:
        got["error"] = 1  # type: ignore[assignment]  # the messages stay unread and are met again as duplicates, which is harmless
    return got


def job_score(s: Session, ctx: Ctx) -> dict:
    now, n, scorer = ctx.now(s), 0, ctx.scorer(s)
    for app in scoring_service.unscored(s):
        scoring_service.score_application(s, app, "scorer", now, scorer)
        n += 1
    return {"scored": n}


def job_retention(s: Session, ctx: Ctx) -> dict:
    st = ctx.settings
    return {"deleted": retention.sweep(s, ctx.now(s), st.retention_days, export_dir=st.export_dir, open_days=st.open_retention_days)}


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
