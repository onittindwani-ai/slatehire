"""Applicant intake: every route in (paste, file, CSV, mailbox, ATS pull, signed webhook) ends here. The resume is redacted before anything reads it."""

from __future__ import annotations

import hashlib
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from slatehire import redaction
from slatehire.errors import RuleError
from slatehire.ingest import Applicant
from slatehire.models import Application, Candidate, IntakeLog, Resume, Role
from slatehire.untrusted import find_injection
from sendora_core.audit import record_audit
from sendora_core.events import record_event


def next_code(s: Session) -> str:
    n = len(list(s.scalars(select(Candidate.id)))) + 1
    while s.scalars(select(Candidate).where(Candidate.code == f"C{n:04d}")).first():
        n += 1
    return f"C{n:04d}"


def _dupe(s: Session, a: Applicant, role: Role, text: str) -> bool:
    """The same application again: the same outside reference, or the same name, email and resume text for the same role."""
    if a.external_ref and s.scalars(select(Candidate).where(Candidate.external_ref == a.external_ref)).first():
        return True
    q = (select(Resume).join(Application, Application.id == Resume.application_id).join(Candidate, Candidate.id == Application.candidate_id)
         .where(Application.role_id == role.id, func.lower(Candidate.full_name) == a.name.strip().lower()))
    if a.email:
        q = q.where(Candidate.email == a.email.strip().lower())
    return any((r.original_text or "").strip() == text for r in s.scalars(q))  # with no email, the same name and the same resume is still the same application


EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def problem(a: Applicant) -> str | None:
    """Plain words for why an applicant cannot be added, or None. Checked before anything is stored."""
    if len((a.name or "").strip()) < 2:
        return "The name is empty. Write the full name."
    if a.email and not EMAIL.fullmatch(a.email.strip()):
        return f"'{a.email.strip()[:60]}' is not an email address. Fix it or leave it empty."
    if len((a.resume_text or "").strip()) < 40:
        return "The resume has too little text to read."
    return None


def add_applicant(s: Session, a: Applicant, role: Role, actor: str, now, *, code: str | None = None, settings=None) -> tuple[Application | None, str]:
    """Returns (application, status). status is added, duplicate or rejected. Nothing is scored or moved here."""
    text = (a.resume_text or "").strip()
    why = problem(a)
    if why:
        s.add(IntakeLog(source=a.source or "paste", ref=(a.external_ref or a.email or a.name or "unknown")[:160], status="rejected", detail=why[:300], created_at=now))
        return None, "rejected"
    if _dupe(s, a, role, text):
        s.add(IntakeLog(source=a.source or "paste", ref=(a.external_ref or a.email or a.name)[:160], status="duplicate", detail="Already applied for this role.", created_at=now))
        return None, "duplicate"
    cand = Candidate(code=code or next_code(s), full_name=a.name.strip(), email=a.email.strip().lower(), phone=a.phone, school=a.school, source=a.source or "paste", external_ref=a.external_ref, created_at=now)
    s.add(cand)
    s.flush()
    app = Application(candidate_id=cand.id, role_id=role.id, stage="applied", history=[{"stage": "applied", "by": actor, "at": now.isoformat(), "note": "Applied."}], created_at=now, updated_at=now)
    s.add(app)
    s.flush()
    inst = settings.redact_institutions if settings is not None else True
    red = redaction.redact(text, [a.name], [a.school] if a.school else None, institutions=inst)
    inj = find_injection(red.redacted)
    s.add(Resume(application_id=app.id, original_text=text, redacted_text=red.redacted, segments=red.segments, counts=red.counts, redaction_version=red.version, filename=a.filename,
                 injection=[{"why": f.why, "text": red.redacted[f.start:f.end][:160]} for f in inj]))
    s.add(IntakeLog(source=a.source or "paste", ref=(a.external_ref or a.email or cand.code)[:160], status="added", detail=f"{cand.code} for {role.key}", created_at=now))
    record_audit(s, actor, "applicant.added", f"application:{app.id}", {"code": cand.code, "role": role.key, "source": a.source or "paste", "resume_sha": hashlib.sha256(text.encode()).hexdigest()[:12]})
    record_event(s, "applicant.added", "application", app.id, {"role": role.key})
    return app, "added"


def role_by_key(s: Session, key: str) -> Role:
    r = s.scalars(select(Role).where(Role.key == key)).first()
    if r is None:
        raise RuleError(f"There is no role '{key}'. Create it first.")
    return r
