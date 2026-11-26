"""Stage moves. A person makes every move and every outcome. There is no function here, and none anywhere else, that moves an application because of a score."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from slatehire import interviews, rubric_service, scoring_service
from slatehire.attention import LANGUAGE, REASON, RESUME_MISSING, attention_of
from slatehire.errors import RuleError, need_person
from slatehire.models import TERMINAL, Application, Interview, Offer, Scorecard
from sendora_core.audit import record_audit
from sendora_core.events import record_event
from sendora_core.models import Approval

ALLOWED = {"applied": ("shortlisted", "declined", "withdrawn"), "shortlisted": ("interviewing", "declined", "withdrawn"), "interviewing": ("offer", "declined", "withdrawn"), "offer": ("hired", "declined", "withdrawn")}
NEED_NOTE = {"declined", "withdrawn"}
LABEL = {"applied": "Applied", "shortlisted": "Shortlisted", "interviewing": "Interviewing", "offer": "Offer", "hired": "Hired", "declined": "Declined", "withdrawn": "Withdrawn"}


def reached(app: Application, stage: str) -> bool:
    return any(h["stage"] == stage for h in app.history)


def scorecard_people(s: Session, application_id: int) -> int:
    ids = [i for (i,) in s.execute(select(Interview.id).where(Interview.application_id == application_id))]
    if not ids:
        return 0
    return len(set(s.scalars(select(Scorecard.interviewer).where(Scorecard.interview_id.in_(ids)))))


def move(s: Session, app: Application, to: str, actor: str, note: str, now, settings) -> Application:
    need_person(actor)
    if app.stage in TERMINAL:
        raise RuleError(f"This application is already {app.stage}. It cannot move again.")
    if to not in ALLOWED.get(app.stage, ()):
        names = [LABEL[x] for x in ALLOWED.get(app.stage, ())]
        raise RuleError(f"From {LABEL.get(app.stage, app.stage)} you can move to {', '.join(names[:-1])} or {names[-1]}.")
    note = (note or "").strip()
    if to in NEED_NOTE and len(note) < 8:
        raise RuleError("Write the reason in your own words (at least a short sentence). A person decides every outcome and the reason is kept.")
    if to == "shortlisted" and attention_of(app) == RESUME_MISSING:
        raise RuleError(REASON[RESUME_MISSING])  # said as it is: the applicant has no resume to read, not "score them first"
    if to == "shortlisted" and attention_of(app) != LANGUAGE:  # a resume in another language is read by a person, who may shortlist without a score
        rub = rubric_service.latest(s, app.role_id, locked_only=True)
        if rub is None or scoring_service.latest_score(s, app.id, rub.id) is None:
            raise RuleError("Score this applicant under the locked rubric before shortlisting.")
    if to == "offer":
        need = settings.min_scorecards
        have = scorecard_people(s, app.id)
        if have < need:
            raise RuleError(f"An offer needs scorecards from at least {need} interviewers. There are {have}.")
    if to == "hired":
        offer = s.scalars(select(Offer).where(Offer.application_id == app.id)).first()
        if offer is None or offer.status != "handed_off":
            raise RuleError("Mark someone hired only after their approved offer was handed off to your signing tool.")
    app.history = [*app.history, {"stage": to, "by": actor, "at": now.isoformat(), "note": note}]
    app.stage, app.updated_at = to, now
    if to in NEED_NOTE:
        _close_offer(s, app, actor, now)
        interviews.cancel_open(s, app, actor)
    if to in TERMINAL or to == "shortlisted":
        app.decided_by, app.decision_note = actor, note
    s.flush()
    record_audit(s, actor, f"application.{to}", f"application:{app.id}", {"from": app.history[-2]["stage"], "note_chars": len(note)})  # the words stay on the application, where a delete removes them; the append only log holds no free text
    record_event(s, "application.moved", "application", app.id, {"to": to})
    return app


def _close_offer(s: Session, app: Application, actor: str, now) -> None:
    """Someone who left the process gets no offer. A draft, a waiting approval or an approved offer that was not handed off is withdrawn, and a waiting request is closed so nobody approves it later."""
    offer = s.scalars(select(Offer).where(Offer.application_id == app.id)).first()
    if offer is None or offer.status not in ("draft", "pending_approval", "approved"):
        return
    ap = s.get(Approval, offer.approval_id) if offer.approval_id else None
    if ap is not None and ap.status == "pending":
        ap.status, ap.decided_by, ap.decided_at = "rejected", actor, now
        ap.decision_note = "Closed: the candidate left the process."
    offer.status = "withdrawn"
    record_audit(s, actor, "offer.withdrawn", f"offer:{offer.id}", {"why": "candidate left the process"})


def funnel(s: Session, role_id: int | None = None) -> dict[str, int]:
    q = select(Application.stage, func.count()).group_by(Application.stage)
    if role_id:
        q = q.where(Application.role_id == role_id)
    got = dict(s.execute(q).all())
    return {st: int(got.get(st, 0)) for st in ("applied", "shortlisted", "interviewing", "offer", "hired", "declined", "withdrawn")}
