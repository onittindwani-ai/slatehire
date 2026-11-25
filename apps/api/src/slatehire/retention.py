"""Retention and delete. Personal details, the resume, the free text written about a person and the offer file are removed; the stage, the dates and the audit log stay,
because they hold no identity (they use the neutral code)."""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from slatehire.errors import RuleError, need_person
from slatehire.models import TERMINAL, Application, Candidate, Demographic, IntakeLog, Interview, Offer, Resume, Score, Scorecard
from sendora_core.audit import record_audit

OPEN_STAGES = ("applied", "shortlisted", "interviewing", "offer")
GONE = "(deleted)"


def _without(text: str, name: str) -> str:
    """The text with the full name and every part of it (first name, last name) replaced, as whole words, so a first name alone does not stay behind."""
    if not text or not name or not name.strip():
        return text
    out = text.replace(name, GONE)
    for token in {t for t in re.split(r"[\s,.\-]+", name) if len(t) >= 3}:
        out = re.sub(rf"(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])", GONE, out, flags=re.I)
    return out


def _rewrite_offer_file(export_dir: str | Path | None, offer: Offer) -> bool:
    """The file written for the signing tool carried the name and the pay terms. It is rewritten from the scrubbed offer text."""
    ref = offer.handoff_ref or ""
    if not export_dir or not ref or "/" in ref or "\\" in ref:
        return False
    path = Path(export_dir) / ref
    if not path.is_file():
        return False
    path.write_text((offer.body or "") + "\n", encoding="utf-8")
    return True


def purge(s: Session, app: Application, actor: str, now, why: str, export_dir: str | Path | None = None) -> None:
    """Delete one candidate's personal data. Core updates are used on scorecards on purpose: the ORM guard protects them from edits, not from a deletion order."""
    cand = s.get(Candidate, app.candidate_id)
    if cand.purged_at is not None:
        raise RuleError("This candidate was already deleted.")
    name, email, ref, code = cand.full_name, cand.email, cand.external_ref, cand.code
    s.execute(delete(Resume).where(Resume.application_id == app.id))
    s.execute(delete(Demographic).where(Demographic.application_id == app.id))
    for sc in s.scalars(select(Score).where(Score.application_id == app.id)):
        sc.items = [{**it, "quotes": [], "rationale": "Removed when the candidate was deleted."} for it in sc.items]
        sc.flags = []
    ids = [i for (i,) in s.execute(select(Interview.id).where(Interview.application_id == app.id))]
    if ids:
        s.execute(update(Scorecard).where(Scorecard.interview_id.in_(ids)).values(comments={}))
    for o in s.scalars(select(Offer).where(Offer.application_id == app.id)):
        o.body, o.terms = _without(o.body, name), _without(o.terms, name)
        _rewrite_offer_file(export_dir, o)
    refs = [r for r in {email, name, ref, code} if r]
    if refs:
        s.execute(delete(IntakeLog).where(IntakeLog.ref.in_([r[:160] for r in refs])))  # the intake list kept the address or the name of this person
    # What people wrote about the person goes too; the stage names, who moved them and when stay.
    app.history = [{k: v for k, v in h.items() if k != "note"} | {"note": ""} for h in app.history]
    app.decision_note = ""
    app.note = ""
    cand.full_name, cand.email, cand.phone, cand.school, cand.external_ref, cand.purged_at = GONE, "", "", "", None, now
    s.flush()
    record_audit(s, actor, "candidate.deleted", f"application:{app.id}", {"code": code, "why": why[:120]})


def _aware(value, now):
    return value if value.tzinfo else value.replace(tzinfo=now.tzinfo)


def sweep(s: Session, now, days: int, *, export_dir: str | Path | None = None, open_days: int = 0) -> int:
    """Delete people whose application ended (declined or withdrawn) more than `days` ago, and the people nobody decided on for more than `open_days`
    (0 means never). Hired people are not touched: that is an employment record, your own rules apply. Intake list rows older than `days` are removed too."""
    n = 0
    cut = now - timedelta(days=days)
    open_cut = now - timedelta(days=open_days) if open_days > 0 else None
    stages = [t for t in TERMINAL if t != "hired"] + (list(OPEN_STAGES) if open_cut is not None else [])
    for app in s.scalars(select(Application).where(Application.stage.in_(stages))):
        limit = cut if app.stage in TERMINAL else open_cut
        cand = s.get(Candidate, app.candidate_id)
        if cand.purged_at is None and limit is not None and _aware(app.updated_at, now) < limit:
            purge(s, app, "retention-job", now, f"older than {days if app.stage in TERMINAL else open_days} days", export_dir)
            n += 1
    for row in s.scalars(select(IntakeLog)):
        if _aware(row.created_at, now) < cut:
            s.delete(row)
    return n
