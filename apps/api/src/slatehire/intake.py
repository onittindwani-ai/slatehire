"""Applicant intake: every route in (paste, file, CSV, mailbox, ATS pull, signed webhook) ends here. The resume is redacted before anything reads it."""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from slatehire import language, redaction, suppression
from slatehire.errors import RuleError
from slatehire.ingest import LANGUAGE_NOTE, MISSING_RESUME, RESUME_MISSING_NOTE, Applicant
from slatehire.models import Application, Candidate, IntakeLog, Resume, Role
from slatehire.textclean import clean_text, one_line, safe_ref
from slatehire.untrusted import INJECTION_SCAN, entries, find_injection
from sendora_core.audit import record_audit
from sendora_core.events import record_event


# Applicants who arrive without a person typing them in. A resume nobody could read must not make such a person vanish: they enter flagged instead (see add_applicant).
AUTOMATIC_SOURCES = frozenset({"email", "ashby", "workable", "greenhouse"})


def next_code(s: Session) -> str:
    n = (s.scalar(select(func.max(Candidate.id))) or 0) + 1
    while s.scalars(select(Candidate).where(Candidate.code == f"C{n:04d}")).first():
        n += 1
    return f"C{n:04d}"


def _dupe(s: Session, a: Applicant, role: Role, text: str) -> bool:
    """The same application again: the same outside reference, or the same name, email and resume text for the same role."""
    if a.external_ref and s.scalars(select(Candidate).where(Candidate.external_ref == a.external_ref, Candidate.source == (a.source or "paste"))).first():
        return True  # the same reference from the same source: a reference sent by an outsider (a Message-ID) can never suppress an ATS applicant
    q = (select(Resume).join(Application, Application.id == Resume.application_id).join(Candidate, Candidate.id == Application.candidate_id)
         .where(Application.role_id == role.id, func.lower(Candidate.full_name) == a.name.strip().lower()))
    if a.email:
        q = q.where(Candidate.email == a.email.strip().lower())
    return any((r.original_text or "").strip() == text for r in s.scalars(q))  # with no email, the same name and the same resume is still the same application


ERASED_DETAIL = "This person was deleted earlier (on request or by the retention rule), so they were not added again. If they applied again on purpose, the owner can lift this: see docs/13."
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


def clean_applicant(a: Applicant) -> Applicant:
    """Every outside string is cut to its column and stripped of line breaks and control characters, on every route in. A name with a line break must never add a
    paragraph to an offer letter, and an over long Message-ID or file name must never make the database refuse a whole batch."""
    return replace(a, name=one_line(a.name, 200), email=one_line(a.email, 254), phone=one_line(a.phone, 60), school=one_line(a.school, 200), role_key=one_line(a.role_key, 40),
                   filename=one_line(a.filename, 200), source=one_line(a.source, 80) or "paste", external_ref=safe_ref(a.external_ref, 120), resume_text=clean_text(a.resume_text, 60_000))


def _is_missing(a: Applicant, text: str) -> bool:
    """A resume nobody could read, for someone who arrived by email or from an ATS and has a name and an address: the person enters, flagged."""
    if a.extra.get("resume_missing"):
        return True
    return len(text) < 40 and a.source in AUTOMATIC_SOURCES and len(a.name) >= 2 and bool(EMAIL.fullmatch(a.email))


def add_applicant(s: Session, a: Applicant, role: Role, actor: str, now, *, code: str | None = None, settings=None) -> tuple[Application | None, str]:
    """Returns (application, status). status is added, duplicate or rejected. Nothing is scored or moved here."""
    a = clean_applicant(a)
    text = (a.resume_text or "").strip()
    missing = _is_missing(a, text)
    if missing:
        a, text = replace(a, resume_text=MISSING_RESUME), MISSING_RESUME
    why = problem(a)
    if why:
        s.add(IntakeLog(source=a.source or "paste", ref=(a.email or a.name or a.external_ref or "unknown")[:160], status="rejected", detail=why[:300], created_at=now))
        return None, "rejected"
    if suppression.is_suppressed(s, a.email, a.source or "paste", a.external_ref):
        s.add(IntakeLog(source=a.source or "paste", ref="erased applicant", status="rejected", detail=ERASED_DETAIL, created_at=now))  # nothing readable about the person is written down again
        return None, "rejected"
    if _dupe(s, a, role, text):
        s.add(IntakeLog(source=a.source or "paste", ref=(a.email or a.name or a.external_ref or "unknown")[:160], status="duplicate", detail="Already applied for this role.", created_at=now))
        return None, "duplicate"
    cand = Candidate(code=code or next_code(s), full_name=a.name.strip(), email=a.email.strip().lower(), phone=a.phone, school=a.school, source=a.source or "paste", external_ref=a.external_ref, created_at=now)
    s.add(cand)
    s.flush()
    lang = "en" if missing else language.detect(text)
    flag = RESUME_MISSING_NOTE if missing else LANGUAGE_NOTE if lang == "other" else ""
    app = Application(candidate_id=cand.id, role_id=role.id, stage="applied", history=[{"stage": "applied", "by": actor, "at": now.isoformat(), "note": "Applied."}], note=flag, created_at=now, updated_at=now)
    s.add(app)
    s.flush()
    inst = settings.redact_institutions if settings is not None else True
    red = redaction.redact(text, [a.name], [a.school] if a.school else None, institutions=inst)
    inj = find_injection(red.redacted)
    s.add(Resume(application_id=app.id, original_text=text, redacted_text=red.redacted, segments=red.segments, counts=red.counts, redaction_version=red.version, filename=a.filename,
                 injection=entries(red.redacted, inj), injection_scan=INJECTION_SCAN, language=lang))
    note = ". The resume could not be read, so the applicant is flagged." if missing else ". The resume is not in English, so it is not scored: a person reads it." if lang == "other" else ""
    s.add(IntakeLog(source=a.source or "paste", ref=(a.email or cand.code)[:160], status="added", detail=f"{cand.code} for {role.key}" + note, created_at=now))
    record_audit(s, actor, "applicant.added", f"application:{app.id}", {"code": cand.code, "role": role.key, "source": a.source or "paste", "resume_sha": hashlib.sha256(text.encode()).hexdigest()[:12]})
    record_event(s, "applicant.added", "application", app.id, {"role": role.key})
    return app, "added"


def role_by_key(s: Session, key: str) -> Role:
    r = s.scalars(select(Role).where(Role.key == key)).first()
    if r is None:
        raise RuleError(f"There is no role '{key}'. Create it first.")
    return r
