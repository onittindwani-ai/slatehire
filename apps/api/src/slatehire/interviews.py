"""Interview kits, scheduling and structured scorecards.

Every candidate for a role gets the same questions in the same order (the kit comes from the locked rubric). Scorecards are written by the
interviewer alone, cannot be changed after they are sent, and the totals are added up by code. An interviewer sees the others' ratings only after sending their own.
"""

from __future__ import annotations

from datetime import datetime
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from slatehire import rubric_service, scoring_service
from slatehire.errors import RuleError, need_person
from slatehire.models import Application, Candidate, Interview, Role, Rubric, Scorecard
from sendora_core.adapters import AdapterError
from sendora_core.audit import record_audit
from sendora_core.safety import SafetyError

PROBES = ("What exactly did you do yourself, as opposed to the team?", "What was the result, and how do you know?", "What would you do differently now?")
RECOMMENDATIONS = ("strong_yes", "yes", "no", "strong_no")


def make_kit(criteria: list[dict]) -> list[dict]:
    """Same for every candidate of the role: one question per criterion, what a 1, 3 and 5 sounds like, and three neutral probes."""
    kit = []
    for c in criteria:
        q = (c.get("question") or "").strip() or f"Tell me about a time you showed {c['name'].lower()}. What did you do and what happened?"
        kit.append({"criterion_id": c["id"], "name": c["name"], "weight": c["weight"], "question": q, "anchors": c["anchors"], "probes": list(PROBES)})
    return kit


def probe_areas(s: Session, app: Application) -> list[dict]:
    """Where the resume gave little to go on (not found, or a low level). Names criteria only: no identity, no guess about the person."""
    rub = rubric_service.latest(s, app.role_id, locked_only=True)
    sc = scoring_service.latest_score(s, app.id, rub.id) if rub else None
    if rub is not None and sc is None:  # scored under an earlier version: its areas still apply, under that version's names
        sc = scoring_service.latest_score(s, app.id)
        rub = s.get(Rubric, sc.rubric_id) if sc else rub
    if not sc:
        return []
    by_id = {c["id"]: c["name"] for c in rub.criteria}
    return [{"criterion_id": it["criterion_id"], "name": by_id.get(it["criterion_id"], it["criterion_id"]), "why": "The resume does not show this." if it["state"] != "scored" else "The resume only shows a low level of this."}
            for it in sc.items if it["state"] != "scored" or (it.get("value") or 0) <= 2]


def plan(s: Session, app: Application, actor: str, interviewers: list[str], starts_at: datetime | None, minutes: int, kind: str, now) -> Interview:
    need_person(actor)
    if app.stage not in ("shortlisted", "interviewing"):
        raise RuleError("Only shortlisted people are interviewed. Shortlist this applicant first.")
    rub = rubric_service.latest(s, app.role_id, locked_only=True)
    if rub is None:
        raise RuleError("The role has no locked rubric.")
    people = sorted({p.strip().lower() for p in interviewers if p.strip()})
    if not people or any("@" not in p for p in people):
        raise RuleError("Name at least one interviewer by email address.")
    if not 15 <= minutes <= 240:
        raise RuleError("An interview is between 15 and 240 minutes.")
    if starts_at is not None and starts_at.date() < now.date():
        raise RuleError("The start time is in the past. Pick a day that has not passed.")
    row = Interview(application_id=app.id, kind=kind, interviewers=people, starts_at=starts_at, minutes=minutes, status="planned", kit=make_kit(rub.criteria), created_by=actor, created_at=now)
    s.add(row)
    s.flush()
    record_audit(s, actor, "interview.planned", f"interview:{row.id}", {"application": app.id, "interviewers": len(people)})
    return row


def invite(s: Session, ctx, interview: Interview, actor: str, confirm: bool) -> dict:
    """Send the calendar invite. This invites a real person, so it needs live mode, the kill switch off and an explicit confirm."""
    need_person(actor)
    app = s.get(Application, interview.application_id)
    if interview.status in ("invited", "done"):
        return {"sent": False, "already": True, "reason": "The invite for this interview was already sent. Nothing was sent again."}
    if interview.status != "planned":
        raise RuleError(f"This interview is {interview.status}, so no invite is sent.")
    if app.stage not in ("shortlisted", "interviewing"):
        raise RuleError("Only shortlisted people are invited. This applicant is no longer in the interview stages.")
    if ctx.effective(s).kill_switch:
        return {"sent": False, "reason": "The kill switch is on, so no invite was sent."}
    cand = s.get(Candidate, app.candidate_id)
    role = s.get(Role, app.role_id)
    if interview.starts_at is None:
        raise RuleError("Set a start time first.")
    if not cand.email:
        raise RuleError("This candidate has no email address, so there is nobody to invite.")
    try:
        out = ctx.adapter(s, "calendar").create_event(title=f"{role.title}: interview", starts_at=interview.starts_at, minutes=interview.minutes, attendees=[cand.email, *interview.interviewers], note="Structured interview. Same questions for every candidate.", confirm=confirm)
    except (SafetyError, AdapterError) as exc:
        return {"sent": False, "reason": str(exc)}
    interview.status, interview.calendar_ref, interview.calendar_detail = "invited", out["ref"], out["detail"][:300]
    record_audit(s, actor, "interview.invited", f"interview:{interview.id}", {"ref": out["ref"]})
    return {"sent": True, "reason": out["detail"]}


def cancel_open(s: Session, app: Application, actor: str) -> int:
    """Interviews that were planned or invited for someone who left the process are cancelled, so nobody sits in a call for a person who was declined. Done interviews stay as they are."""
    n = 0
    for iv in s.scalars(select(Interview).where(Interview.application_id == app.id, Interview.status.in_(("planned", "invited")))):
        iv.status = "cancelled"
        record_audit(s, actor, "interview.cancelled", f"interview:{iv.id}", {"why": "candidate left the process"})
        n += 1
    return n


def submit_scorecard(s: Session, interview: Interview, actor: str, ratings: dict, comments: dict, recommendation: str, now) -> Scorecard:
    need_person(actor)
    if interview.status == "cancelled":
        raise RuleError("This interview was cancelled because the candidate left the process.")
    who = actor.lower()
    if who not in interview.interviewers:
        raise RuleError("Only a named interviewer can send a scorecard for this interview.")
    if s.scalars(select(Scorecard).where(Scorecard.interview_id == interview.id, Scorecard.interviewer == who)).first():
        raise RuleError("You already sent a scorecard for this interview. It cannot be changed.")
    ids = [k["criterion_id"] for k in interview.kit]
    clean: dict[str, int] = {}
    for cid in ids:
        v = ratings.get(cid)
        if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 5:
            raise RuleError("Rate every criterion with a whole number from 1 to 5.")
        clean[cid] = v
    if set(ratings) - set(ids):
        raise RuleError("A rating names a criterion that is not in this interview.")
    if recommendation not in RECOMMENDATIONS:
        raise RuleError("Choose a recommendation: strong yes, yes, no or strong no.")
    row = Scorecard(interview_id=interview.id, interviewer=who, ratings=clean, comments={k: str(v)[:600] for k, v in (comments or {}).items() if k in ids}, recommendation=recommendation, created_at=now)
    s.add(row)
    s.flush()
    if len(s.scalars(select(Scorecard).where(Scorecard.interview_id == interview.id)).all()) >= len(interview.interviewers):
        interview.status = "done"
    record_audit(s, who, "scorecard.sent", f"interview:{interview.id}", {})  # that one was sent, never what it says: the log can be read by people who have not sent theirs
    return row


def aggregate(interview: Interview, cards: list[Scorecard], weights: dict[str, int]) -> dict:
    """All sums are code. spread is the highest minus the lowest rating for a criterion, and 2 or more is flagged as a disagreement to talk about."""
    per = []
    for k in interview.kit:
        vals = [c.ratings[k["criterion_id"]] for c in cards if k["criterion_id"] in c.ratings]
        per.append({"criterion_id": k["criterion_id"], "name": k["name"], "mean": round(mean(vals), 2) if vals else None, "min": min(vals) if vals else None, "max": max(vals) if vals else None, "spread": (max(vals) - min(vals)) if vals else 0, "disagree": bool(vals) and max(vals) - min(vals) >= 2, "n": len(vals)})
    wsum = sum(weights.get(p["criterion_id"], 1) for p in per if p["mean"] is not None)
    overall = round(100 * sum(weights.get(p["criterion_id"], 1) * p["mean"] for p in per if p["mean"] is not None) / (5 * wsum), 1) if wsum else None
    tally = {r: sum(1 for c in cards if c.recommendation == r) for r in RECOMMENDATIONS}
    return {"criteria": per, "overall": overall, "recommendations": tally, "submitted": len(cards), "invited": len(interview.interviewers), "complete": len(cards) >= len(interview.interviewers), "disagreements": [p["name"] for p in per if p["disagree"]]}


def view(s: Session, interview: Interview, actor: str) -> dict:
    """What `actor` may see. Individual ratings and the totals stay hidden from an interviewer until they have sent their own."""
    cards = list(s.scalars(select(Scorecard).where(Scorecard.interview_id == interview.id).order_by(Scorecard.id)))
    app = s.get(Application, interview.application_id)
    rub = rubric_service.latest(s, app.role_id, locked_only=True)
    weights = {c["id"]: c["weight"] for c in rub.criteria} if rub else {}
    mine = next((c for c in cards if c.interviewer == actor.lower()), None)
    is_interviewer = actor.lower() in interview.interviewers
    open_view = (not is_interviewer) or mine is not None
    out = {"id": interview.id, "submitted_by": [c.interviewer for c in cards], "my_scorecard": None if mine is None else {"ratings": mine.ratings, "comments": mine.comments, "recommendation": mine.recommendation}, "can_submit": is_interviewer and mine is None, "hidden": not open_view}
    if open_view:
        out["scorecards"] = [{"interviewer": c.interviewer, "ratings": c.ratings, "comments": c.comments, "recommendation": c.recommendation} for c in cards]
        out["summary"] = aggregate(interview, cards, weights)
    return out
