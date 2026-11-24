"""The 30, 60 and 90 day plan. A template with a few role specific lines. A person edits it, owns each task and ticks it off."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from slatehire.errors import RuleError, need_person
from slatehire.models import Application, OnboardingTask, Role
from sendora_core.audit import record_audit

# (phase, days after the start date, task, default owner)
BASE = [
    (30, 1, "Laptop, accounts and building access are ready on day one", "IT"),
    (30, 3, "Meet the team and the person who will be your buddy", "Hiring manager"),
    (30, 7, "Read the handbook and sign the policies", "People ops"),
    (30, 14, "Finish the first small piece of real work with a reviewer", "Buddy"),
    (30, 28, "Thirty day conversation: what is clear, what is not", "Hiring manager"),
    (60, 40, "Own one recurring task from start to finish", "Hiring manager"),
    (60, 45, "Meet two people outside the team to learn how work reaches you", "Buddy"),
    (60, 56, "Sixty day conversation: goals for the next thirty days", "Hiring manager"),
    (90, 70, "Lead one improvement and write down what changed", "Hiring manager"),
    (90, 80, "Give feedback on how the first months went", "People ops"),
    (90, 88, "Ninety day review against the goals you agreed", "Hiring manager"),
]
BY_ROLE = {
    "support": [(30, 5, "Shadow ten support conversations and read the help articles", "Buddy"), (60, 50, "Answer your own queue with a reviewer reading a sample", "Buddy")],
    "ops": [(30, 6, "Sit in on one supplier call and one scheduling meeting", "Buddy"), (60, 52, "Run one weekly schedule alone", "Hiring manager")],
    "analyst": [(30, 5, "Get read access to the data and run the standard weekly queries", "Buddy"), (60, 50, "Present one analysis to the people who asked for it", "Hiring manager")],
}


def create_plan(s: Session, app: Application, actor: str, start: date) -> list[OnboardingTask]:
    need_person(actor)
    if app.stage != "hired":
        raise RuleError("An onboarding plan is made for someone who has been hired.")
    if s.scalars(select(OnboardingTask).where(OnboardingTask.application_id == app.id)).first():
        raise RuleError("This person already has an onboarding plan.")
    role = s.get(Role, app.role_id)
    rows = []
    for phase, off, title, owner in sorted([*BASE, *BY_ROLE.get(role.key, [])], key=lambda x: (x[0], x[1])):
        t = OnboardingTask(application_id=app.id, phase=phase, title=title, owner=owner, due_on=(start + timedelta(days=off)).isoformat(), origin="template")
        s.add(t)
        rows.append(t)
    s.flush()
    record_audit(s, actor, "onboarding.planned", f"application:{app.id}", {"tasks": len(rows), "start": start.isoformat()})
    return rows


def add_task(s: Session, app: Application, actor: str, phase: int, title: str, owner: str, due_on: str) -> OnboardingTask:
    need_person(actor)
    if phase not in (30, 60, 90):
        raise RuleError("The phase is 30, 60 or 90.")
    try:
        date.fromisoformat(due_on)
    except ValueError as exc:
        raise RuleError("Write the due date as YYYY-MM-DD.") from exc
    if len(title.strip()) < 5:
        raise RuleError("Describe the task in a few words.")
    t = OnboardingTask(application_id=app.id, phase=phase, title=title.strip()[:300], owner=owner.strip()[:120] or "Hiring manager", due_on=due_on, origin="added")
    s.add(t)
    s.flush()
    record_audit(s, actor, "onboarding.task_added", f"task:{t.id}", {})
    return t


def progress(tasks: list[OnboardingTask], today: date) -> dict:
    out = {}
    for ph in (30, 60, 90):
        ts = [t for t in tasks if t.phase == ph]
        out[str(ph)] = {"total": len(ts), "done": sum(1 for t in ts if t.done), "overdue": sum(1 for t in ts if not t.done and date.fromisoformat(t.due_on) < today)}
    return out
