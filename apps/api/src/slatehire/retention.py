"""Retention and delete. Personal details and the resume are removed; the stage, the dates and the audit log stay, because they hold no identity (they use the neutral code)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from slatehire.errors import RuleError, need_person
from slatehire.models import TERMINAL, Application, Candidate, Demographic, Interview, Offer, Resume, Score, Scorecard
from sendora_core.audit import record_audit


def _without(text: str, name: str) -> str:
    return text.replace(name, "(deleted)") if name and name.strip() else text


def purge(s: Session, app: Application, actor: str, now, why: str) -> None:
    """Delete one candidate's personal data. Core updates are used on scorecards on purpose: the ORM guard protects them from edits, not from a deletion order."""
    cand = s.get(Candidate, app.candidate_id)
    if cand.purged_at is not None:
        raise RuleError("This candidate was already deleted.")
    s.execute(delete(Resume).where(Resume.application_id == app.id))
    s.execute(delete(Demographic).where(Demographic.application_id == app.id))
    for sc in s.scalars(select(Score).where(Score.application_id == app.id)):
        sc.items = [{**it, "quotes": [], "rationale": "Removed when the candidate was deleted."} for it in sc.items]
        sc.flags = []
    ids = [i for (i,) in s.execute(select(Interview.id).where(Interview.application_id == app.id))]
    if ids:
        s.execute(update(Scorecard).where(Scorecard.interview_id.in_(ids)).values(comments={}))
    name = cand.full_name
    for o in s.scalars(select(Offer).where(Offer.application_id == app.id)):
        o.body, o.terms = _without(o.body, name), _without(o.terms, name)
    cand.full_name, cand.email, cand.phone, cand.school, cand.external_ref, cand.purged_at = "(deleted)", "", "", "", None, now
    app.note = ""
    s.flush()
    record_audit(s, actor, "candidate.deleted", f"application:{app.id}", {"code": cand.code, "why": why[:120]})


def sweep(s: Session, now, days: int) -> int:
    """Delete people whose application ended (declined or withdrawn) more than `days` ago. Hired people are not touched: that is an employment record, your own rules apply."""
    n = 0
    cut = now - timedelta(days=days)
    for app in s.scalars(select(Application).where(Application.stage.in_([t for t in TERMINAL if t != "hired"]))):
        u = app.updated_at if app.updated_at.tzinfo else app.updated_at.replace(tzinfo=now.tzinfo)
        cand = s.get(Candidate, app.candidate_id)
        if u < cut and cand.purged_at is None:
            purge(s, app, "retention-job", now, f"older than {days} days")
            n += 1
    return n
