from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from slatehire import fairness_service, interviews, pipeline, rubric_service, scoring_service
from slatehire.api.deps import db, get_ctx, get_or_404, user, writer
from slatehire.api.serializers import blind_enforced, iso, person, pieces, row, source_label
from slatehire.context import Ctx
from slatehire.models import Application, Candidate, FairnessReport, IntakeLog, Interview, OnboardingTask, Offer, Resume, Role, Rubric, Score
from slatehire.onboarding import progress
from sendora_core.audit import record_audit
from sendora_core.auth import WRITE_ROLES
from sendora_core.models import Approval, AuditEntry

router = APIRouter(prefix="/api", tags=["read"])
STAGES = ("applied", "shortlisted", "interviewing", "offer", "hired")


def _role_ctx(s: Session):
    roles = {r.id: r for r in s.scalars(select(Role))}
    rubs = {rid: (rubric_service.latest(s, rid, locked_only=True)) for rid in roles}
    return roles, rubs


def stale_jobs(s: Session) -> list[str]:
    """Recurring jobs (the mailbox, scoring, the retention sweep) that have not finished for three of their own intervals. If the worker is stopped or a job keeps failing,
    nobody is told by silence: this is the list the top of the page shows."""
    from sendora_core.db import utcnow
    from sendora_core.models import Job
    from slatehire.jobs import INTERVALS

    now, late = utcnow(), []
    for kind, secs in INTERVALS.items():
        last = s.scalars(select(Job).where(Job.kind == kind, Job.status == "done").order_by(Job.id.desc())).first()
        newest = s.scalars(select(Job).where(Job.kind == kind).order_by(Job.id.desc())).first()
        if newest is None:
            continue  # never queued: a worker that was never started is shown by the worker health, not here
        ref = last.finished_at if last is not None and last.finished_at else newest.created_at
        if (now - (ref if ref.tzinfo else ref.replace(tzinfo=now.tzinfo))).total_seconds() > 3 * secs:
            late.append(kind)
    return late


@router.get("/overview", summary="Numbers for the top of the page")
def overview(s: Session = Depends(db), ctx: Ctx = Depends(get_ctx)):
    roles, rubs = _role_ctx(s)
    funnel = pipeline.funnel(s)
    pend = s.scalar(select(func.count()).select_from(Approval).where(Approval.status == "pending")) or 0
    q = scoring_service.quote_check(s)
    return {"funnel": funnel, "roles": len(roles), "roles_unlocked": sum(1 for r in rubs.values() if r is None), "pending_approvals": pend, "unscored": len(scoring_service.unscored(s)), "evidence": {"quotes": q["quotes"], "invalid": q["invalid"], "valid_percent": q["valid_percent"]},
            "stale_jobs": stale_jobs(s), "today": ctx.today(s).isoformat(), "overdue_tasks": sum(1 for t in s.scalars(select(OnboardingTask).where(OnboardingTask.done.is_(False))) if date.fromisoformat(t.due_on) < ctx.today(s))}


@router.get("/intake/log", summary="Every application that came in by email, an ATS or a form and was not added, with the reason (owner and approver). Nobody leaves the funnel without a line here.")
def intake_log(status: str | None = Query(None, pattern="^(added|duplicate|rejected)$"), limit: int = Query(100, ge=1, le=500), s: Session = Depends(db), u: dict = Depends(writer)):
    q = select(IntakeLog).order_by(IntakeLog.id.desc()).limit(limit)
    if status:
        q = q.where(IntakeLog.status == status)
    else:
        q = q.where(IntakeLog.status != "added")
    return [{"id": r.id, "source": r.source, "ref": r.ref, "status": r.status, "detail": r.detail, "at": iso(r.created_at)} for r in s.scalars(q)]


@router.get("/roles", summary="Roles with their rubric state")
def roles(s: Session = Depends(db)):
    out = []
    for r in s.scalars(select(Role).order_by(Role.id)):
        lat, lock = rubric_service.latest(s, r.id), rubric_service.latest(s, r.id, locked_only=True)
        cnt = pipeline.funnel(s, r.id)
        out.append({"id": r.id, "key": r.key, "title": r.title, "team": r.team, "status": r.status, "description": r.description, "job_post": r.job_post, "applicants": sum(cnt.values()), "funnel": cnt,
                    "rubric": None if lat is None else {"id": lat.id, "version": lat.version, "locked": lat.locked, "blind": lat.blind}, "scoring_rubric": None if lock is None else lock.version})
    return out


def _rubric(r: Rubric) -> dict:
    return {"id": r.id, "role_id": r.role_id, "version": r.version, "criteria": r.criteria, "locked": r.locked, "locked_by": r.locked_by, "locked_at": iso(r.locked_at), "fingerprint": r.fingerprint, "blind": r.blind,
            "redaction_version": r.redaction_version, "signature_ok": rubric_service.verify_signature(r) if r.locked else None}


@router.get("/roles/{role_id}/rubrics", summary="Every version of the rubric for a role")
def rubrics(role_id: int, s: Session = Depends(db)):
    get_or_404(s, Role, role_id, "role")
    return [_rubric(r) for r in s.scalars(select(Rubric).where(Rubric.role_id == role_id).order_by(Rubric.version.desc()))]


@router.get("/pipeline", summary="Cards for the board: the top of each stage, with the real count")
def board(role: str | None = None, per_stage: int = Query(40, ge=1, le=200), s: Session = Depends(db)):
    roles, rubs = _role_ctx(s)
    q = select(Application)
    if role:
        q = q.where(Application.role_id.in_([r.id for r in roles.values() if r.key == role]))
    out = {st: {"count": 0, "cards": []} for st in STAGES}
    scores, newest = {}, {}
    for sc in s.scalars(select(Score).order_by(Score.id)):
        scores[(sc.application_id, sc.rubric_id)] = sc
        newest[sc.application_id] = sc
    cands = {c.id: c for c in s.scalars(select(Candidate))}
    rows = []
    for app in s.scalars(q):
        if app.stage not in out:
            continue
        rub = rubs.get(app.role_id)
        sc = (scores.get((app.id, rub.id)) if rub else None) or newest.get(app.id)  # a person scored under an earlier version keeps that score until read again
        rows.append((app, sc))
    rows.sort(key=lambda x: (-(x[1].total if x[1] else -1), x[0].id))
    for app, sc in rows:
        col = out[app.stage]
        col["count"] += 1
        if len(col["cards"]) < per_stage:
            c, hide = cands[app.candidate_id], blind_enforced(s, app)
            col["cards"].append({"id": app.id, "code": c.code, "name": person(c, hide)["name"], "hidden": hide, "role": roles[app.role_id].key, "role_title": roles[app.role_id].title, "total": sc.total if sc else None, "flags": len(sc.flags) if sc else 0, "stage": app.stage})
    out["closed"] = {"declined": pipeline.funnel(s, None)["declined"], "withdrawn": pipeline.funnel(s, None)["withdrawn"]}
    return out


@router.get("/applications", summary="Every application, for the table")
def applications(role: str | None = None, stage: str | None = None, limit: int = Query(20000, ge=1, le=50000), s: Session = Depends(db)):
    roles, rubs = _role_ctx(s)
    q = select(Application, Candidate).join(Candidate, Candidate.id == Application.candidate_id).order_by(Application.id)
    if stage:
        q = q.where(Application.stage == stage)
    if role:
        q = q.where(Application.role_id.in_([r.id for r in roles.values() if r.key == role]))
    scores, newest = {}, {}
    for sc in s.scalars(select(Score).order_by(Score.id)):
        scores[(sc.application_id, sc.rubric_id)] = sc
        newest[sc.application_id] = sc
    out = []
    for app, c in s.execute(q.limit(limit)).all():
        rub = rubs.get(app.role_id)
        sc = (scores.get((app.id, rub.id)) if rub else None) or newest.get(app.id)
        hide = blind_enforced(s, app) if rub else False
        p = person(c, hide)
        out.append({"id": app.id, "code": c.code, "name": p["name"], "hidden": hide, "role": roles[app.role_id].key, "role_title": roles[app.role_id].title, "stage": app.stage, "total": sc.total if sc else None, "covered": sc.covered if sc else None,
                    "flags": len(sc.flags) if sc else 0, "source": source_label(c, hide), "updated_at": iso(app.updated_at), "deleted": c.purged_at is not None,
                    "attention": "resume_missing" if (app.note or "").startswith("Resume missing") else None})
    return out


def _audit_reveal(s: Session, who: str, app_id: int) -> None:
    """A reveal is written to the audit log once per person, application and ten minutes. The page asks again whenever it refreshes, and each refresh must not add another line."""
    target = f"application:{app_id}"
    last = s.scalars(select(AuditEntry).where(AuditEntry.action == "identity.revealed", AuditEntry.actor == who, AuditEntry.target == target).order_by(AuditEntry.id.desc())).first()
    if last is not None:
        try:
            at = datetime.fromisoformat(last.created_at)
            at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - at < timedelta(minutes=10):
                return
        except ValueError:
            pass
    record_audit(s, who, "identity.revealed", target, {})


@router.get("/applications/{app_id}", summary="One candidate workspace. Identity is hidden while blind mode is enforced.")
def workspace(app_id: int, reveal: bool = False, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(user)):
    app = get_or_404(s, Application, app_id, "application")
    c, role = s.get(Candidate, app.candidate_id), s.get(Role, app.role_id)
    enforced = blind_enforced(s, app)
    if reveal and u["role"] not in WRITE_ROLES:
        raise HTTPException(403, "A read only sign in cannot show identities. Ask an owner or an approver.")
    hide = enforced or not reveal
    if reveal and not enforced:
        _audit_reveal(s, u["user"], app.id)
    rub = rubric_service.latest(s, app.role_id, locked_only=True)
    sc = scoring_service.latest_score(s, app.id, rub.id) if rub else None
    shown = rub
    if rub is not None and sc is None:  # scored under an earlier version: show that score with the version it was made under
        old = scoring_service.latest_score(s, app.id)
        if old is not None:
            sc, shown = old, s.get(Rubric, old.rubric_id)
    res = s.scalars(select(Resume).where(Resume.application_id == app.id)).first()
    ivs = list(s.scalars(select(Interview).where(Interview.application_id == app.id).order_by(Interview.id)))
    offer = s.scalars(select(Offer).where(Offer.application_id == app.id)).first()
    tasks = list(s.scalars(select(OnboardingTask).where(OnboardingTask.application_id == app.id).order_by(OnboardingTask.phase, OnboardingTask.due_on)))
    return {
        "id": app.id, "stage": app.stage, "role": {"key": role.key, "title": role.title}, "person": person(c, hide), "blind": {"enforced": enforced, "showing": hide, "rubric_setting": bool(rub and rub.blind)},
        "history": app.history, "decided_by": app.decided_by, "decision_note": app.decision_note, "note": app.note, "deleted": c.purged_at is not None,
        "rubric": None if shown is None else {"id": shown.id, "version": shown.version, "fingerprint": shown.fingerprint, "signature_ok": rubric_service.verify_signature(shown), "blind": shown.blind, "criteria": shown.criteria},
        "current_version": None if rub is None else rub.version,
        "score": None if sc is None else {"id": sc.id, "total": sc.total, "covered": sc.covered, "items": sc.items, "flags": sc.flags, "scorer": sc.scorer, "at": iso(sc.created_at)},
        "resume": {"pieces": pieces(res, sc.items if sc else [], reveal=not hide), "counts": res.counts if res else {}, "injection": res.injection if res else [], "filename": ("" if res is None else "resume file" if hide and res.filename else res.filename)},  # a file name often carries the person's name
        "probe_areas": interviews.probe_areas(s, app), "interviews": [{"id": i.id, "kind": i.kind, "starts_at": iso(i.starts_at), "minutes": i.minutes, "status": i.status, "interviewers": i.interviewers, "calendar_detail": i.calendar_detail} for i in ivs],
        "offer": None if offer is None else {"id": offer.id, "status": offer.status, "title": offer.title, "start_date": offer.start_date, "handoff_ref": offer.handoff_ref},
        "onboarding": {"tasks": [{"id": t.id, "phase": t.phase, "title": t.title, "owner": t.owner, "due_on": t.due_on, "done": t.done} for t in tasks], "progress": progress(tasks, ctx.today(s))} if tasks else None,
    }


@router.get("/interviews", summary="Interviews with who sent a scorecard")
def interview_list(s: Session = Depends(db)):
    out = []
    for i in s.scalars(select(Interview).order_by(Interview.id.desc())):
        app = s.get(Application, i.application_id)
        c, role = s.get(Candidate, app.candidate_id), s.get(Role, app.role_id)
        hide = blind_enforced(s, app)
        v = interviews.view(s, i, "nobody@none")
        out.append({"id": i.id, "application_id": app.id, "name": person(c, hide)["name"], "code": c.code, "role": role.title, "kind": i.kind, "starts_at": iso(i.starts_at), "minutes": i.minutes, "status": i.status, "interviewers": i.interviewers, "sent": v["submitted_by"]})
    return out


@router.get("/interviews/{interview_id}", summary="One interview: the kit, and the scorecards the signed in person may see")
def interview_one(interview_id: int, s: Session = Depends(db), u: dict = Depends(user)):
    i = get_or_404(s, Interview, interview_id, "interview")
    app = s.get(Application, i.application_id)
    c, role = s.get(Candidate, app.candidate_id), s.get(Role, app.role_id)
    return {"id": i.id, "application_id": app.id, "name": person(c, blind_enforced(s, app))["name"], "role": role.title, "kind": i.kind, "starts_at": iso(i.starts_at), "minutes": i.minutes, "status": i.status, "interviewers": i.interviewers,
            "kit": i.kit, "probe_areas": interviews.probe_areas(s, app), "calendar_detail": i.calendar_detail, **interviews.view(s, i, u["user"])}


@router.get("/offers", summary="Offers")
def offer_list(s: Session = Depends(db)):
    out = []
    for o in s.scalars(select(Offer).order_by(Offer.id.desc())):
        app = s.get(Application, o.application_id)
        c = s.get(Candidate, app.candidate_id)
        ap = s.get(Approval, o.approval_id) if o.approval_id else None
        out.append({"id": o.id, "application_id": app.id, "name": c.full_name, "code": c.code, "title": o.title, "start_date": o.start_date, "status": o.status, "terms": o.terms, "body": o.body, "handoff_ref": o.handoff_ref, "created_by": o.created_by,
                    "approval": None if ap is None else {"id": ap.id, "status": ap.status, "requested_by": ap.requested_by, "decided_by": ap.decided_by}})
    return out


@router.get("/onboarding", summary="Onboarding plans")
def onboarding_list(s: Session = Depends(db), ctx: Ctx = Depends(get_ctx)):
    out = []
    today = ctx.today(s)
    for app in s.scalars(select(Application).where(Application.id.in_(select(OnboardingTask.application_id).distinct()))):
        c, role = s.get(Candidate, app.candidate_id), s.get(Role, app.role_id)
        ts = list(s.scalars(select(OnboardingTask).where(OnboardingTask.application_id == app.id).order_by(OnboardingTask.phase, OnboardingTask.due_on)))
        out.append({"application_id": app.id, "name": c.full_name, "role": role.title, "progress": progress(ts, today), "today": today.isoformat(),
                    "tasks": [{"id": t.id, "phase": t.phase, "title": t.title, "owner": t.owner, "due_on": t.due_on, "done": t.done, "overdue": (not t.done) and date.fromisoformat(t.due_on) < today} for t in ts]})
    return out


@router.get("/fairness", summary="The latest fairness report, if one was run, and the latest one that flagged a group")
def fairness_latest(role: str = "all", s: Session = Depends(db), ctx: Ctx = Depends(get_ctx)):
    reports = list(s.scalars(select(FairnessReport).where(FairnessReport.role_key == role).order_by(FairnessReport.id.desc())))
    rep = reports[0] if reports else None
    flagged = next((r for r in reports if r.payload.get("flagged")), None)  # a newer clean report must not bury an older one that flagged a group
    labelled = fairness_service.labelled_count(s)

    def view(r: FairnessReport | None):
        return None if r is None else {"id": r.id, "created_at": iso(r.created_at), "created_by": r.created_by, "payload": r.payload}

    return {"report": view(rep), "latest_flagged": view(flagged) if flagged is not None and flagged is not rep else None, "labelled": labelled, "min_group_floor": ctx.settings.fairness_min_group,
            "history": [{"id": r.id, "role": r.role_key, "at": iso(r.created_at), "flagged": len(r.payload.get("flagged", []))} for r in s.scalars(select(FairnessReport).order_by(FairnessReport.id.desc()).limit(10))]}


@router.get("/evals", summary="Quote check, computed now over every stored score")
def evals(s: Session = Depends(db)):
    return {"quote_check": scoring_service.quote_check(s)}
