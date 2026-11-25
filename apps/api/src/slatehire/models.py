"""Slatehire tables (prefix cf_). They sit on the shared Base.

Demographic data lives in its own table and is read only by `fairness_service`. A test enforces that.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from sendora_core.db import Base, UTCDateTime, utcnow

STAGES = ("applied", "shortlisted", "interviewing", "offer", "hired", "declined", "withdrawn")
TERMINAL = ("hired", "declined", "withdrawn")
REACHED = {"shortlisted": ("shortlisted", "interviewing", "offer", "hired"), "interviewed": ("interviewing", "offer", "hired"), "offered": ("offer", "hired"), "hired": ("hired",)}


class State(Base):
    __tablename__ = "cf_state"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Role(Base):
    __tablename__ = "cf_role"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(160))
    team: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(16), default="open")
    description: Mapped[str] = mapped_column(Text, default="")
    job_post: Mapped[str] = mapped_column(Text, default="")
    ats_job_id: Mapped[str] = mapped_column(String(120), default="", server_default="")  # the job in your ATS that this role is; an ATS pull for the role brings in only the people who applied to it
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Rubric(Base):
    __tablename__ = "cf_rubric"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("cf_role.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    criteria: Mapped[list] = mapped_column(JSON)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    locked_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(32), default="")
    blind: Mapped[bool] = mapped_column(Boolean, default=True)  # part of the signature: identity stays hidden until the shortlist decision
    redaction_version: Mapped[str] = mapped_column(String(10), default="1")  # part of the signature too
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Candidate(Base):
    __tablename__ = "cf_candidate"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)  # stable neutral id shown while blind
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    school: Mapped[str] = mapped_column(String(200), default="")
    source: Mapped[str] = mapped_column(String(80), default="")
    external_ref: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    purged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Application(Base):
    __tablename__ = "cf_application"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("cf_candidate.id"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("cf_role.id"), index=True)
    stage: Mapped[str] = mapped_column(String(20), default="applied", index=True)
    history: Mapped[list] = mapped_column(JSON, default=list)  # [{stage, by, at, note}]
    decided_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    fairness_folded: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")  # True once this person's counts were added to the fairness totals (see fairness_service.fold)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Resume(Base):
    __tablename__ = "cf_resume"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("cf_application.id"), unique=True)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # removed by the retention job
    redacted_text: Mapped[str] = mapped_column(Text)
    segments: Mapped[list] = mapped_column(JSON, default=list)
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    redaction_version: Mapped[str] = mapped_column(String(10), default="1")
    filename: Mapped[str] = mapped_column(String(200), default="")
    injection: Mapped[list] = mapped_column(JSON, default=list)  # each entry: why, text, and where it sits in redacted_text (start, end) once injection_scan is 1
    injection_scan: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # 1: the lines that talk to the scorer were found when the resume was saved and their places are stored; 0: an older row, read once and then stored
    language: Mapped[str] = mapped_column(String(10), default="en", server_default="en")  # en, other (the scorer reads English only, so nothing is scored) or unknown (too short to tell)
    notes: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")  # what the reader of the file found: hidden text, which attachment was used and why, a body that was ignored. Each: {kind, detail, private}


class ResumeFile(Base):
    """The resume file as it arrived (a PDF, size capped), kept so a person can look at what a reader could not show (hidden text, a layout). It holds the name and contact
    details, so it is shown only when identity is not hidden, and it is erased with the person."""
    __tablename__ = "cf_resume_file"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("cf_application.id"), unique=True)
    media_type: Mapped[str] = mapped_column(String(40), default="application/pdf")
    content: Mapped[bytes] = mapped_column(LargeBinary)


class Score(Base):
    __tablename__ = "cf_score"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("cf_application.id"), index=True)
    rubric_id: Mapped[int] = mapped_column(ForeignKey("cf_rubric.id"), index=True)
    items: Mapped[list] = mapped_column(JSON)
    total: Mapped[float] = mapped_column(Float)
    covered: Mapped[int] = mapped_column(Integer, default=0)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    scorer: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Interview(Base):
    __tablename__ = "cf_interview"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("cf_application.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40), default="structured")
    interviewers: Mapped[list] = mapped_column(JSON, default=list)
    starts_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    minutes: Mapped[int] = mapped_column(Integer, default=45)
    status: Mapped[str] = mapped_column(String(20), default="planned")  # planned, invited, done, cancelled
    kit: Mapped[list] = mapped_column(JSON, default=list)
    calendar_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    calendar_detail: Mapped[str] = mapped_column(String(300), default="")
    created_by: Mapped[str] = mapped_column(String(254), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Scorecard(Base):
    __tablename__ = "cf_scorecard"
    __table_args__ = (UniqueConstraint("interview_id", "interviewer", name="uq_cf_scorecard_one_per_interviewer"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("cf_interview.id"), index=True)
    interviewer: Mapped[str] = mapped_column(String(254))
    ratings: Mapped[dict] = mapped_column(JSON)  # criterion id -> 1..5
    comments: Mapped[dict] = mapped_column(JSON, default=dict)
    recommendation: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Offer(Base):
    __tablename__ = "cf_offer"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("cf_application.id"), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[str] = mapped_column(String(10))
    terms: Mapped[str] = mapped_column(Text)  # written by a person, never by the system
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft, pending_approval, approved, handed_off, rejected
    approval_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    handoff_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_by: Mapped[str] = mapped_column(String(254), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class OnboardingTask(Base):
    __tablename__ = "cf_onboarding_task"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("cf_application.id"), index=True)
    phase: Mapped[int] = mapped_column(Integer)  # 30, 60 or 90
    title: Mapped[str] = mapped_column(String(300))
    owner: Mapped[str] = mapped_column(String(120), default="Hiring manager")
    due_on: Mapped[str] = mapped_column(String(10))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    done_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    origin: Mapped[str] = mapped_column(String(40), default="template")


class Demographic(Base):
    """Voluntary group labels. Read only by fairness_service."""
    __tablename__ = "cf_demographic"
    application_id: Mapped[int] = mapped_column(ForeignKey("cf_application.id"), primary_key=True)
    group_label: Mapped[str] = mapped_column(String(60))


class FairnessReport(Base):
    __tablename__ = "cf_fairness_report"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_key: Mapped[str] = mapped_column(String(40), default="all")
    min_group: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(254), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class FairnessAggregate(Base):
    """What a deleted person added to the fairness counts, kept without a name, an address or a day: role, step, group label, month. Without it every deletion would turn a labelled
    person into nothing and the report would drift toward "too few" as people are deleted (see fairness_service.fold)."""
    __tablename__ = "cf_fairness_aggregate"
    __table_args__ = (UniqueConstraint("role_id", "step", "group_label", "month", name="uq_cf_fairness_aggregate"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("cf_role.id"), index=True)
    step: Mapped[str] = mapped_column(String(20))
    group_label: Mapped[str] = mapped_column(String(60))
    month: Mapped[str] = mapped_column(String(7))
    entered: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    people: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class IntakeLog(Base):
    __tablename__ = "cf_intake_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(40))
    ref: Mapped[str] = mapped_column(String(160), index=True)
    status: Mapped[str] = mapped_column(String(20))  # added, duplicate, rejected
    detail: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Suppression(Base):
    """A person who was erased and must not be added again by a mailbox, an ATS pull or a webhook retry. Holds a keyed one way hash and the date, nothing readable."""
    __tablename__ = "cf_suppression"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(10))  # email or ref (an outside reference such as a Message-ID or an ATS id)
    scheme: Mapped[str] = mapped_column(String(8), default="key", server_default="salt")  # key: made with SUPPRESSION_KEY from the environment; salt: made with the salt that sat in the database (older rows)
    group_id: Mapped[str] = mapped_column(String(32), default="", server_default="")  # the hashes of one erasure share this, so lifting by address also lifts the reference
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
