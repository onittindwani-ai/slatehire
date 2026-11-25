"""Offers. A person writes the terms. The system fills a plain template, asks a second person to approve, and writes a file for the signing tool. It never sends an offer to a candidate."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from slatehire import pipeline
from slatehire.errors import RuleError, need_person
from slatehire.models import Application, Candidate, Offer, Role
from slatehire.textclean import one_line
from sendora_core.approvals import request_approval, require_approved
from sendora_core.audit import record_audit
from sendora_core.safety import KillSwitchError

TEMPLATE = """OFFER OF EMPLOYMENT (DRAFT FOR REVIEW)

From: {company}
To: {name}
Role: {title}
Planned start date: {start}

Terms, as written by the hiring manager:
{terms}

This draft was prepared from a template. It is not legal advice and it has not been reviewed by a lawyer. Have it checked against the employment rules that apply where the person will work before you send it for signing.
"""


def create(s: Session, app: Application, actor: str, title: str, start_date: str, terms: str, today: date, min_scorecards: int, company: str = "") -> Offer:
    need_person(actor)
    if app.stage not in ("interviewing", "offer"):
        raise RuleError("An offer is drafted for someone who has been interviewed.")
    if s.scalars(select(Offer).where(Offer.application_id == app.id)).first():
        raise RuleError("This application already has an offer.")
    have = pipeline.scorecard_people(s, app.id)
    if have < min_scorecards:
        raise RuleError(f"An offer needs scorecards from at least {min_scorecards} interviewers. There are {have}.")
    try:
        d = date.fromisoformat(start_date)
    except ValueError as exc:
        raise RuleError("Write the start date as YYYY-MM-DD.") from exc
    if d <= today:
        raise RuleError("The start date must be in the future.")
    if len((terms or "").strip()) < 20:
        raise RuleError("Write the terms yourself (pay, hours, anything agreed). The system never writes terms.")
    cand = s.get(Candidate, app.candidate_id)
    title = one_line(title, 200)
    body = TEMPLATE.format(company=one_line(company, 120) or "(company name not set)", name=one_line(cand.full_name, 200), title=title, start=start_date, terms=terms.strip())  # one line each: a name can never add a paragraph
    row = Offer(application_id=app.id, title=title, start_date=start_date, terms=terms.strip(), body=body, status="draft", created_by=actor)
    s.add(row)
    s.flush()
    record_audit(s, actor, "offer.drafted", f"offer:{row.id}", {"application": app.id})
    return row


def ask_approval(s: Session, offer: Offer, actor: str) -> Offer:
    need_person(actor)
    if offer.status not in ("draft", "rejected"):
        raise RuleError(f"This offer is {offer.status.replace('_', ' ')}.")
    app = s.get(Application, offer.application_id)
    if app.stage in ("declined", "withdrawn"):
        raise RuleError("This person is no longer in the process, so there is no offer to approve.")
    ap = request_approval(s, "offer.approve", f"Approve offer: {offer.title} for candidate {s.get(Candidate, app.candidate_id).code}", {"offer_id": offer.id}, "high", actor)
    offer.status, offer.approval_id = "pending_approval", ap.id
    s.flush()
    return offer


def hand_off(s: Session, ctx, offer: Offer, actor: str) -> dict:
    need_person(actor)
    if offer.status == "withdrawn":
        raise RuleError("This offer was withdrawn because the person left the process, so no offer file is written.")
    if offer.status != "approved" or offer.approval_id is None:
        raise RuleError("The offer needs an approval from a second person first.")
    app = s.get(Application, offer.application_id)
    if app.stage in ("declined", "withdrawn"):
        raise RuleError("This person is no longer in the process, so no offer file is written.")
    require_approved(s, offer.approval_id, "offer.approve")
    eff = ctx.effective(s)
    if eff.kill_switch:
        raise KillSwitchError("The kill switch is on, so the offer file was not written.")
    cand = s.get(Candidate, app.candidate_id)
    out = ctx.adapter(s, "handoff").hand_off(offer_id=offer.id, title=offer.title, candidate_code=cand.code, body=offer.body)
    offer.status, offer.handoff_ref = "handed_off", out["ref"]
    if app.stage == "interviewing":
        app.history = [*app.history, {"stage": "offer", "by": actor, "at": ctx.now(s).isoformat(), "note": "Offer approved and handed off."}]
        app.stage = "offer"
    record_audit(s, actor, "offer.handed_off", f"offer:{offer.id}", {"ref": out["ref"]})
    return out
