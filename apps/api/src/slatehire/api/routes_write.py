from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from slatehire import fairness_service, ingest, intake, interviews, offers, onboarding, pipeline, retention, rubric_service, scoring_service
from slatehire.adapters.fetch import safe_fetch
from slatehire.api.deps import db, get_ctx, get_or_404, owner, rule, writer
from slatehire.api.routes_read import _rubric
from slatehire.context import Ctx
from slatehire.errors import RuleError
from slatehire.ingest import Applicant
from slatehire.models import Application, Candidate, Interview, OnboardingTask, Offer, Role, Rubric
from sendora_core.adapters import AdapterError
from sendora_core.audit import record_audit

router = APIRouter(prefix="/api", tags=["write"])


# roles and rubrics
class RoleIn(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    team: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=4000)


@router.post("/roles", summary="Create a role with a starter job post")
def create_role(b: RoleIn, s: Session = Depends(db), u: dict = Depends(writer)):
    r = rule(rubric_service.create_role, s, u["user"], b.title, b.team, b.description)
    return {"id": r.id, "key": r.key}


class RoleEdit(BaseModel):
    description: str | None = Field(default=None, max_length=4000)
    job_post: str | None = Field(default=None, max_length=12000)
    status: str | None = Field(default=None, pattern="^(open|closed)$")


@router.put("/roles/{role_id}", summary="Edit the description, the job post or the open or closed state")
def edit_role(role_id: int, b: RoleEdit, s: Session = Depends(db), u: dict = Depends(writer)):
    r = get_or_404(s, Role, role_id, "role")
    for k, v in b.model_dump(exclude_none=True).items():
        setattr(r, k, v)
    record_audit(s, u["user"], "role.edited", f"role:{r.id}", {k: True for k in b.model_dump(exclude_none=True)})
    return {"ok": True}


@router.post("/roles/{role_id}/job-post", summary="Write a fresh job post from the role and the rubric (a template, not a language model)")
def job_post(role_id: int, s: Session = Depends(db), u: dict = Depends(writer)):
    r = get_or_404(s, Role, role_id, "role")
    rub = rubric_service.latest(s, r.id)
    r.job_post = rubric_service.job_post_draft(r, rub.criteria if rub else None)
    return {"job_post": r.job_post}


class CriterionIn(BaseModel):
    id: str = Field(min_length=1, max_length=40, pattern="^[a-z0-9_]+$")
    name: str = Field(max_length=120)
    description: str = Field(default="", max_length=500)
    weight: int
    anchors: dict[str, str]
    look_for: list[str] = []
    question: str = Field(default="", max_length=400)


class RubricIn(BaseModel):
    criteria: list[CriterionIn] | None = None
    blind: bool | None = None


@router.post("/roles/{role_id}/rubric", summary="Start a rubric draft (a new version when one is locked)")
def new_rubric(role_id: int, b: RubricIn, s: Session = Depends(db), u: dict = Depends(writer)):
    role = get_or_404(s, Role, role_id, "role")
    prev = rubric_service.latest(s, role.id)
    if prev is not None and prev.locked:
        r = rule(rubric_service.new_version, s, role, u["user"])
        if b.criteria is not None or b.blind is not None:
            rule(rubric_service.edit, s, r, u["user"], [c.model_dump() for c in b.criteria] if b.criteria is not None else None, b.blind)
    else:
        r = rule(rubric_service.new_draft, s, role, u["user"], [c.model_dump() for c in b.criteria] if b.criteria is not None else None, b.blind)
    return _rubric(r)


@router.put("/rubrics/{rubric_id}", summary="Edit an unlocked rubric")
def edit_rubric(rubric_id: int, b: RubricIn, s: Session = Depends(db), u: dict = Depends(writer)):
    r = get_or_404(s, Rubric, rubric_id, "rubric")
    return _rubric(rule(rubric_service.edit, s, r, u["user"], [c.model_dump() for c in b.criteria] if b.criteria is not None else None, b.blind))


@router.post("/rubrics/{rubric_id}/check", summary="Plain language problems that would stop a lock")
def check_rubric(rubric_id: int, s: Session = Depends(db)):
    from slatehire import rubrics

    r = get_or_404(s, Rubric, rubric_id, "rubric")
    return {"problems": rubrics.validate(r.criteria)}


@router.post("/rubrics/{rubric_id}/lock", summary="Lock the rubric. A person does this; after it, nothing in it can change.")
def lock_rubric(rubric_id: int, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    r = get_or_404(s, Rubric, rubric_id, "rubric")
    return _rubric(rule(rubric_service.lock, s, r, u["user"], ctx.now(s)))


# intake
class PasteIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: str = Field(default="", max_length=254)
    phone: str = Field(default="", max_length=60)
    school: str = Field(default="", max_length=200)
    role: str
    resume_text: str = Field(default="", max_length=60000)
    resume_url: str = Field(default="", max_length=500)


def _intake(s: Session, ctx: Ctx, a: Applicant, role_key: str, actor: str):
    role = rule(intake.role_by_key, s, role_key)
    why = intake.problem(a)
    app, status = intake.add_applicant(s, a, role, actor, ctx.now(s), settings=ctx.settings)
    return {"status": status, "application_id": app.id if app else None, "reason": why}


@router.post("/applicants", summary="Add one applicant by pasting the resume or giving a web address")
def add_one(b: PasteIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    text = b.resume_text
    if not text and b.resume_url:
        try:
            text = rule(ingest.text_from_bytes, safe_fetch(b.resume_url, allow_http_local=ctx.settings.allow_http_local_targets), b.resume_url.rsplit("/", 1)[-1] or "resume.txt")
        except (AdapterError, ingest.IngestError) as exc:
            raise HTTPException(400, str(exc)) from exc
    a = Applicant(b.name, b.email, b.phone, b.role, text, "", "paste", b.school)
    return _intake(s, ctx, a, b.role, u["user"])


@router.post("/applicants/file", summary="Upload one resume file (text, markdown or PDF) for a role")
async def add_file(request: Request, role: str, name: str, email: str = "", s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    fn = (request.headers.get("x-filename") or "resume.txt")[:200]
    data = await request.body()
    if len(data) > ctx.settings.upload_max_bytes:
        raise HTTPException(413, "The file is larger than the limit.")
    try:
        text = ingest.text_from_bytes(data, fn)
    except ingest.IngestError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _intake(s, ctx, Applicant(name, email, "", role, text, fn, "upload"), role, u["user"])


@router.post("/applicants/csv", summary="Upload a CSV: name, email, phone, role, resume_text, source, school")
async def add_csv(request: Request, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    data = await request.body()
    if len(data) > ctx.settings.upload_max_bytes:
        raise HTTPException(413, "The file is larger than the limit.")
    try:
        rows = ingest.from_csv(data)
    except ingest.IngestError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not rows:
        raise HTTPException(400, "The file has no applicant rows. Use a header line with the columns name, email, phone, role, resume_text, source, school, then one line per person.")
    out = {"added": 0, "duplicate": 0, "rejected": 0, "problems": []}
    for i, a in enumerate(rows, 2):
        try:
            role = intake.role_by_key(s, a.role_key)
        except RuleError as exc:
            out["rejected"] += 1
            out["problems"].append(f"Row {i}: {exc}")
            continue
        why = intake.problem(a)
        _app, st = intake.add_applicant(s, a, role, u["user"], ctx.now(s), settings=ctx.settings)
        if st == "rejected" and why and len(out["problems"]) < 20:
            out["problems"].append(f"Row {i}: {why}")
        out[st] += 1
    return out


@router.post("/intake/mailbox", summary="Read new application emails now")
def read_mailbox(s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    from slatehire.jobs import job_mailbox

    return job_mailbox(s, ctx)


@router.post("/intake/ats", summary="Pull applicants from the ATS you selected (read only)")
def pull_ats(role: str, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    r = rule(intake.role_by_key, s, role)
    try:
        found = ctx.adapter(s, "ats").list_applicants()
    except AdapterError as exc:
        raise HTTPException(502, str(exc)) from exc
    out = {"added": 0, "duplicate": 0, "rejected": 0}
    for a in found:
        _app, st = intake.add_applicant(s, a, r, u["user"], ctx.now(s), settings=ctx.settings)
        out[st] += 1
    return out


# decisions
class ScoreIn(BaseModel):
    pass


@router.post("/applications/{app_id}/score", summary="Score under the locked rubric (an aid; it never moves anyone)")
def score(app_id: int, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    app = get_or_404(s, Application, app_id, "application")
    sc = rule(scoring_service.score_application, s, app, u["user"], ctx.now(s), ctx.scorer(s))
    return {"id": sc.id, "total": sc.total, "covered": sc.covered}


class MoveIn(BaseModel):
    to: str = Field(pattern="^(shortlisted|interviewing|offer|hired|declined|withdrawn)$")
    note: str = Field(default="", max_length=600)


@router.post("/applications/{app_id}/move", summary="A person moves an application. Declining or withdrawing needs a written reason.")
def move(app_id: int, b: MoveIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    app = get_or_404(s, Application, app_id, "application")
    rule(pipeline.move, s, app, b.to, u["user"], b.note, ctx.now(s), ctx.settings)
    plan = 0
    if b.to == "hired":  # the 30, 60 and 90 day plan starts with the hire, from the planned start date
        o = s.scalars(select(Offer).where(Offer.application_id == app.id)).first()
        plan = len(rule(onboarding.create_plan, s, app, u["user"], date.fromisoformat(o.start_date) if o else ctx.today(s)))
    return {"stage": app.stage, "onboarding_tasks": plan}


@router.delete("/candidates/{app_id}", summary="Delete a candidate's personal data now (owner)")
def delete_candidate(app_id: int, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(owner)):
    app = get_or_404(s, Application, app_id, "application")
    rule(retention.purge, s, app, u["user"], ctx.now(s), "deleted on request")
    for o in s.scalars(select(Offer).where(Offer.application_id == app.id)):  # the file written for the signing tool carried the name too
        ref = o.handoff_ref or ""
        path = Path(ctx.settings.export_dir) / ref
        if ref and "/" not in ref and "\\" not in ref and path.is_file():
            path.write_text(o.body + "\n", encoding="utf-8")
    return {"ok": True}


# interviews
class InterviewIn(BaseModel):
    interviewers: list[str] = Field(min_length=1, max_length=8)
    starts_at: datetime | None = None
    minutes: int = 45
    kind: str = Field(default="structured", pattern="^(structured|screen|panel)$")


@router.post("/applications/{app_id}/interviews", summary="Plan an interview. The kit is the same for everyone in the role.")
def plan_interview(app_id: int, b: InterviewIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    app = get_or_404(s, Application, app_id, "application")
    when = b.starts_at.astimezone(timezone.utc) if b.starts_at and b.starts_at.tzinfo else (b.starts_at.replace(tzinfo=timezone.utc) if b.starts_at else None)
    iv = rule(interviews.plan, s, app, u["user"], b.interviewers, when, b.minutes, b.kind, ctx.now(s))
    if app.stage == "shortlisted":
        rule(pipeline.move, s, app, "interviewing", u["user"], "Interview planned.", ctx.now(s), ctx.settings)
    return {"id": iv.id}


class InviteIn(BaseModel):
    confirm: bool = False


@router.post("/interviews/{interview_id}/invite", summary="Send the calendar invite. Needs live mode and an explicit confirm; draft mode sends nothing.")
def invite(interview_id: int, b: InviteIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    iv = get_or_404(s, Interview, interview_id, "interview")
    return rule(interviews.invite, s, ctx, iv, u["user"], b.confirm)


class ScorecardIn(BaseModel):
    ratings: dict[str, int]
    comments: dict[str, str] = {}
    recommendation: str


@router.post("/interviews/{interview_id}/scorecards", summary="Send your scorecard. It cannot be changed after.")
def scorecard(interview_id: int, b: ScorecardIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    iv = get_or_404(s, Interview, interview_id, "interview")
    rule(interviews.submit_scorecard, s, iv, u["user"], b.ratings, b.comments, b.recommendation, ctx.now(s))
    return {"ok": True}


# offers
class OfferIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    start_date: str
    terms: str = Field(max_length=4000)


@router.post("/applications/{app_id}/offer", summary="Draft an offer. A person writes the terms.")
def draft_offer(app_id: int, b: OfferIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    app = get_or_404(s, Application, app_id, "application")
    o = rule(offers.create, s, app, u["user"], b.title, b.start_date, b.terms, ctx.today(s), ctx.settings.min_scorecards)
    return {"id": o.id}


@router.post("/offers/{offer_id}/request-approval", summary="Ask a second person to approve the offer")
def offer_approval(offer_id: int, s: Session = Depends(db), u: dict = Depends(writer)):
    o = get_or_404(s, Offer, offer_id, "offer")
    return {"status": rule(offers.ask_approval, s, o, u["user"]).status}


@router.post("/offers/{offer_id}/hand-off", summary="Write the approved offer to a file for your signing tool. Nothing is sent to the candidate.")
def hand_off(offer_id: int, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    o = get_or_404(s, Offer, offer_id, "offer")
    return rule(offers.hand_off, s, ctx, o, u["user"])


# onboarding
@router.post("/applications/{app_id}/onboarding", summary="Make the 30, 60, 90 day plan for someone who was hired")
def make_plan(app_id: int, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    app = get_or_404(s, Application, app_id, "application")
    o = s.scalars(select(Offer).where(Offer.application_id == app.id)).first()
    rows = rule(onboarding.create_plan, s, app, u["user"], date.fromisoformat(o.start_date) if o else ctx.today(s))
    return {"tasks": len(rows)}


class TaskIn(BaseModel):
    phase: int
    title: str = Field(max_length=300)
    owner: str = Field(default="Hiring manager", max_length=120)
    due_on: str


@router.post("/applications/{app_id}/onboarding/tasks", summary="Add a task to a plan")
def add_task(app_id: int, b: TaskIn, s: Session = Depends(db), u: dict = Depends(writer)):
    app = get_or_404(s, Application, app_id, "application")
    return {"id": rule(onboarding.add_task, s, app, u["user"], b.phase, b.title, b.owner, b.due_on).id}


class TaskPatch(BaseModel):
    done: bool


@router.patch("/onboarding/tasks/{task_id}", summary="Tick a task off or reopen it")
def patch_task(task_id: int, b: TaskPatch, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    t = get_or_404(s, OnboardingTask, task_id, "task")
    t.done, t.done_at = b.done, (ctx.now(s) if b.done else None)
    record_audit(s, u["user"], "onboarding.task_done" if b.done else "onboarding.task_reopened", f"task:{t.id}", {})
    return {"done": t.done}


# fairness
class FairnessIn(BaseModel):
    role: str = "all"
    min_group: int = Field(default=10, ge=2, le=200)
    threshold: str = "4/5"


@router.post("/fairness/run", summary="Run the fairness indicator and save the report")
def fairness_run(b: FairnessIn, s: Session = Depends(db), u: dict = Depends(writer)):
    r = rule(fairness_service.run, s, u["user"], b.role, b.min_group, b.threshold)
    return {"id": r.id}


class LabelsIn(BaseModel):
    labels: dict[str, str]


@router.post("/fairness/labels", summary="Import voluntary group labels by candidate code (owner). Nobody is guessed.")
def fairness_labels(b: LabelsIn, s: Session = Depends(db), u: dict = Depends(owner)):
    return rule(fairness_service.set_labels, s, b.labels, u["user"])
