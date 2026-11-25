"""Roles, job posts and rubrics. A person writes or edits the rubric, a person locks it, and nothing is scored until it is locked."""

from __future__ import annotations

import copy
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from slatehire import rubrics
from slatehire.errors import RuleError, need_person
from slatehire.models import Role, Rubric
from slatehire.redaction import VERSION as REDACTION_VERSION
from sendora_core.audit import record_audit


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "role"


def latest(s: Session, role_id: int, locked_only: bool = False) -> Rubric | None:
    q = select(Rubric).where(Rubric.role_id == role_id)
    if locked_only:
        q = q.where(Rubric.locked.is_(True))
    return s.scalars(q.order_by(Rubric.version.desc())).first()


def create_role(s: Session, actor: str, title: str, team: str = "", description: str = "", key: str | None = None, company: str = "") -> Role:
    need_person(actor)
    key = key or slug(title)
    if any(r.title.strip().lower() == title.strip().lower() for r in s.scalars(select(Role))):
        raise RuleError(f"There is already a role called '{title.strip()}'. Open it in its tab, or give this one a different title.")
    if s.scalars(select(Role).where(Role.key == key)).first():
        raise RuleError(f"A role with the key '{key}' already exists.")
    r = Role(key=key, title=title.strip(), team=team.strip(), description=description.strip())
    r.job_post = job_post_draft(r, None, company)
    s.add(r)
    s.flush()
    record_audit(s, actor, "role.created", f"role:{r.id}", {"key": key})
    return r


def job_post_draft(role: Role, criteria: list[dict] | None = None, company: str = "") -> str:
    """A plain job post written from the role and the rubric. A template, not a language model. A person edits it before it is used."""
    lines = [f"# {role.title}", ""]
    if company.strip():
        lines += [f"Company: {company.strip()}", ""]
    if role.team:
        lines += [f"Team: {role.team}", ""]
    lines += [role.description.strip() or "[Write two or three sentences about the work and who it helps.]", "", "## What we will look at", ""]
    for c in criteria or []:
        lines.append(f"- {c['name']}")
    if not criteria:
        lines.append("- [Add the rubric criteria and they will be listed here.]")
    lines += ["", "## How we decide", "", "Every applicant is read against the same written criteria. Names, schools and contact details are hidden from the first read. People make every decision.", "", "## How to apply", "", "[Say where to send a resume.]"]
    return "\n".join(lines)


def new_draft(s: Session, role: Role, actor: str, criteria: list[dict] | None = None, blind: bool | None = None) -> Rubric:
    need_person(actor)
    prev = latest(s, role.id)
    if prev is not None and not prev.locked:
        raise RuleError("This role already has a rubric that is not locked yet. Edit that one.")
    crit = copy.deepcopy(criteria if criteria is not None else (prev.criteria if prev else []))
    row = Rubric(role_id=role.id, version=(prev.version + 1) if prev else 1, criteria=crit, blind=prev.blind if (prev and blind is None) else (True if blind is None else blind), redaction_version=REDACTION_VERSION)
    s.add(row)
    s.flush()
    record_audit(s, actor, "rubric.drafted", f"rubric:{row.id}", {"role": role.key, "version": row.version})
    return row


def edit(s: Session, rubric: Rubric, actor: str, criteria: list[dict] | None = None, blind: bool | None = None) -> Rubric:
    need_person(actor)
    if rubric.locked:
        raise RuleError("A locked rubric cannot be changed. Start a new version and lock it again.")
    if criteria is not None:
        rubric.criteria = criteria
    if blind is not None:
        rubric.blind = blind
    s.flush()
    record_audit(s, actor, "rubric.edited", f"rubric:{rubric.id}", {"criteria": len(rubric.criteria), "blind": rubric.blind})
    return rubric


def lock(s: Session, rubric: Rubric, actor: str, now, company: str = "", extra_terms: list[str] | None = None) -> Rubric:
    """Lock the rubric. After this its criteria, weights, anchors, blind setting and redaction version are fixed and signed by a fingerprint."""
    need_person(actor)
    if rubric.locked:
        raise RuleError("This rubric is already locked.")
    problems = rubrics.validate(rubric.criteria) + rubrics.proxy_problems(rubric.criteria, extra_terms)
    if problems:
        raise RuleError("Fix this before you lock: " + " ".join(problems))
    rubric.fingerprint = rubrics.fingerprint(rubric.criteria, rubric.blind, rubric.redaction_version)
    rubric.locked, rubric.locked_by, rubric.locked_at = True, actor, now
    role = s.get(Role, rubric.role_id)
    if role is not None:
        role.job_post = job_post_draft(role, rubric.criteria, company) if "[Add the rubric criteria" in (role.job_post or "") else role.job_post
    s.flush()
    record_audit(s, actor, "rubric.locked", f"rubric:{rubric.id}", {"version": rubric.version, "fingerprint": rubric.fingerprint, "blind": rubric.blind})
    return rubric


def verify_signature(rubric: Rubric) -> bool:
    """True when the stored fingerprint still matches the rubric content. A mismatch means the rows were edited outside the app."""
    return rubric.locked and rubric.fingerprint == rubrics.fingerprint(rubric.criteria, rubric.blind, rubric.redaction_version)


def new_version(s: Session, role: Role, actor: str) -> Rubric:
    prev = latest(s, role.id)
    if prev is None or not prev.locked:
        raise RuleError("There is nothing locked to copy. Edit the draft instead.")
    return new_draft(s, role, actor, copy.deepcopy(prev.criteria), prev.blind)
