"""Applicants who need a person before anything is scored: a resume nobody could read, or one the scorer cannot read (not English). One place says which, so every list and rule agrees."""

from __future__ import annotations

from slatehire.models import Application

RESUME_MISSING = "resume_missing"
LANGUAGE = "language"
MISSING_PREFIX = "Resume missing"
LANGUAGE_PREFIX = "Not scored: language"


def attention_of(app: Application) -> str | None:
    note = app.note or ""
    if note.startswith(MISSING_PREFIX):
        return RESUME_MISSING
    if note.startswith(LANGUAGE_PREFIX):
        return LANGUAGE
    return None


REASON = {
    RESUME_MISSING: "No readable resume arrived for this applicant, so there is nothing to score and they cannot be shortlisted yet. A Word or Pages file is not read here. Ask for a PDF or text version and add the applicant again with it (decline this entry with a reason), or just decline.",
    LANGUAGE: "This resume does not look like English, and the scorer reads English only, so it was not scored. Read it yourself; it can be shortlisted without a score.",
}
