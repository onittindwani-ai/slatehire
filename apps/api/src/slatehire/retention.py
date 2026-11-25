"""Retention and delete. Personal details, the resume, the free text written about a person and the offer file are removed; the stage, the dates and the audit log stay,
because they hold no identity (they use the neutral code)."""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from slatehire import fairness_service, suppression
from slatehire.errors import RuleError, need_person
from slatehire.models import TERMINAL, Application, Candidate, Demographic, IntakeLog, Interview, OnboardingTask, Offer, Resume, ResumeFile, Score, Scorecard
from slatehire.suppression import normalize_email
from sendora_core.audit import record_audit
from sendora_core.models import Approval

OPEN_STAGES = ("applied", "shortlisted", "interviewing", "offer")
GONE = "(deleted)"


def _phone_patterns(phone: str) -> list[re.Pattern]:
    """The phone number in any layout: the digits with anything (spaces, brackets, dots, dashes) between them, with and without the country code."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 6:
        return []
    forms = {digits} | ({digits[-10:]} if len(digits) > 10 else set())
    return [re.compile(r"(?<!\d)\+?" + r"[\s().\-/x]{0,3}".join(re.escape(d) for d in f) + r"(?!\d)") for f in forms]


def _without(text: str, name: str, *private: str) -> str:
    """The text with every copy of the person taken out: the full name (any capitals, any spacing), every part of the name of two or more letters standing on its own, the email address
    in any capitals, and the phone number in any layout. Whatever stands in the other private strings is taken out wherever it appears."""
    if not text:
        return text
    out = text
    phone = private[1] if len(private) > 1 else ""
    for item in (p for p in private[:1] if p and p.strip()):
        out = re.sub(re.escape(item.strip()), GONE, out, flags=re.I)
    for rx in _phone_patterns(phone):
        out = rx.sub(GONE, out)
    if not name or not name.strip():
        return out
    tokens = [t for t in re.split(r"[\s,.\-]+", name.strip()) if len(t) >= 2 and any(ch.isalnum() for ch in t)]
    if len(tokens) > 1:
        out = re.sub(r"(?<!\w)" + r"[\s,.\-]+".join(re.escape(t) for t in tokens) + r"(?!\w)", GONE, out, flags=re.I)
    out = re.sub(re.escape(name.strip()), GONE, out, flags=re.I)
    for token in sorted(set(tokens), key=len, reverse=True):
        out = re.sub(rf"(?<!\w){re.escape(token)}(?!\w)", GONE, out, flags=re.I)
    return out


def _rewrite_offer_file(export_dir: str | Path | None, offer: Offer, code: str) -> bool:
    """The file written for the signing tool carried the name and the pay terms, and its name carried the offer title. It is written again from the scrubbed offer text under a name that
    holds only the neutral code, and the old file is removed."""
    ref = offer.handoff_ref or ""
    if not export_dir or not ref or "/" in ref or "\\" in ref or ref.startswith("."):
        return False
    folder = Path(export_dir)
    old = folder / ref
    if not old.is_file():
        return False
    new_name = f"offer-{offer.id}-{code.lower()}-erased.txt"
    (folder / new_name).write_text((offer.body or "") + "\n", encoding="utf-8")
    if new_name != ref:
        old.unlink()
    offer.handoff_ref = new_name
    return True


def _scrub_offers(s: Session, app: Application, name: str, email: str, phone: str, code: str, export_dir) -> int:
    n = 0
    for o in s.scalars(select(Offer).where(Offer.application_id == app.id)):
        o.title, o.body, o.terms = (_without(x, name, email, phone) for x in (o.title, o.body, o.terms))
        _rewrite_offer_file(export_dir, o, code)
        ap = s.get(Approval, o.approval_id) if o.approval_id else None
        if ap is not None:
            ap.decision_note = None  # what the approver wrote about the offer may carry the name
            ap.summary = _without(ap.summary, name, email, phone)  # "Approve offer: <title> for candidate <code>": the title is typed by a person
        n += 1
    return n


def _purge_one(s: Session, app: Application, actor: str, now, why: str, export_dir) -> dict:
    cand = s.get(Candidate, app.candidate_id)
    if cand.purged_at is not None:
        raise RuleError("This candidate was already deleted.")
    name, email, ref, code, phone, source = cand.full_name, cand.email, cand.external_ref, cand.code, cand.phone, cand.source
    fairness_service.fold(s, app, now)  # their share of the fairness counts is kept, without a name, before the label goes
    gone = {"resumes": int(s.execute(delete(Resume).where(Resume.application_id == app.id)).rowcount or 0), "files": int(s.execute(delete(ResumeFile).where(ResumeFile.application_id == app.id)).rowcount or 0)}
    s.execute(delete(Demographic).where(Demographic.application_id == app.id))
    scores = 0
    for sc in s.scalars(select(Score).where(Score.application_id == app.id)):
        sc.items = [{**it, "quotes": [], "rejected_quotes": [], "rationale": "Removed when the candidate was deleted."} for it in sc.items]  # a rejected quote is a piece of the resume too
        sc.flags = []
        scores += 1
    ids = [i for (i,) in s.execute(select(Interview.id).where(Interview.application_id == app.id))]
    if ids:
        s.execute(update(Scorecard).where(Scorecard.interview_id.in_(ids)).values(comments={}))
        for iv in s.scalars(select(Interview).where(Interview.id.in_(ids))):
            iv.calendar_detail = _without(iv.calendar_detail, name, email, phone)  # what the calendar answered may name the guest
    gone["offers"] = _scrub_offers(s, app, name, email, phone, code, export_dir)
    tasks = 0
    for t in s.scalars(select(OnboardingTask).where(OnboardingTask.application_id == app.id)):
        t.title = _without(t.title, name, email, phone)  # a task a person added by hand ("send the laptop to ...")
        tasks += 1
    gone["scores"], gone["tasks"] = scores, tasks
    refs = [r.lower()[:160] for r in {email, name, ref, code} if r]
    if refs:
        gone["intake_lines"] = int(s.execute(delete(IntakeLog).where(func.lower(IntakeLog.ref).in_(refs))).rowcount or 0)  # the intake list kept the address or the name of this person, in the capitals it was typed in
    # What people wrote about the person goes too; the stage names, who moved them and when stay.
    app.history = [{k: v for k, v in h.items() if k != "note"} | {"note": ""} for h in app.history]
    app.decision_note = ""
    app.note = ""
    gone["suppressed"] = suppression.record(s, email, source, ref, now) > 0
    cand.full_name, cand.email, cand.phone, cand.school, cand.source, cand.external_ref, cand.purged_at = GONE, "", "", "", "", None, now
    s.flush()
    record_audit(s, actor, "candidate.deleted", f"application:{app.id}", {"code": code, "why": why[:120]})
    return gone


def purge(s: Session, app: Application, actor: str, now, why: str, export_dir: str | Path | None = None) -> bool:
    """Delete one candidate's personal data. Core updates are used on scorecards on purpose: the ORM guard protects them from edits, not from a deletion order.
    Returns True when a one way hash of the person was kept so that they are not added again (see suppression.py)."""
    return bool(_purge_one(s, app, actor, now, why, export_dir)["suppressed"])


def purge_person(s: Session, app: Application, actor: str, now, why: str, export_dir: str | Path | None = None) -> dict:
    """Delete a person on request: this application and every other application with the same address (a person who applied for two roles is one person). Returns exactly what was removed."""
    cand = s.get(Candidate, app.candidate_id)
    same = normalize_email(cand.email)
    others: list[Application] = []
    if same:
        for c in s.scalars(select(Candidate).where(Candidate.purged_at.is_(None), Candidate.id != cand.id, func.lower(Candidate.email).like(f"%{same.split('@')[1]}"))):
            if normalize_email(c.email) == same:
                others += list(s.scalars(select(Application).where(Application.candidate_id == c.id).order_by(Application.id)))
    total: dict = {"applications": 0}
    for a in [app, *others]:
        got = _purge_one(s, a, actor, now, why, export_dir)
        total["applications"] += 1
        for k, v in got.items():
            total[k] = (total.get(k, 0) + v) if isinstance(v, int) and not isinstance(v, bool) else (bool(total.get(k)) or bool(v))
    total["also_removed"] = len(others)
    return total


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
