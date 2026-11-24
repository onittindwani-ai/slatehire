"""Score an application against the locked rubric of its role. Input is the redacted resume only. The score is an aid for a person, never a decision."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from slatehire import evidence, rubric_service, scoring
from slatehire.errors import RuleError
from slatehire.models import Application, Resume, Score
from slatehire.redaction import PLACEHOLDER_RE  # noqa: F401  (kept so a reader sees what the scorer never receives)
from slatehire.untrusted import find_injection
from sendora_core.audit import record_audit
from sendora_core.events import record_event


def latest_score(s: Session, application_id: int, rubric_id: int | None = None) -> Score | None:
    q = select(Score).where(Score.application_id == application_id)
    if rubric_id is not None:
        q = q.where(Score.rubric_id == rubric_id)
    return s.scalars(q.order_by(Score.id.desc())).first()


def score_application(s: Session, app: Application, actor: str, now, scorer=None) -> Score:
    rub = rubric_service.latest(s, app.role_id, locked_only=True)
    if rub is None:
        raise RuleError("Lock the rubric for this role before anyone is scored.")
    if not rubric_service.verify_signature(rub):
        raise RuleError("The locked rubric no longer matches its signature. Nothing was scored. Check the audit log.")
    res = s.scalars(select(Resume).where(Resume.application_id == app.id)).first()
    if res is None or not res.redacted_text:
        raise RuleError("There is no resume text for this application (it may have been deleted).")
    out = scoring.score_resume(rub.criteria, res.redacted_text, scorer)  # the scorer sees the REDACTED text only, never the original
    prev = latest_score(s, app.id, rub.id)
    if prev is not None and prev.items == out["items"] and prev.total == out["total"]:
        return prev  # the same text under the same rubric gives the same score, so no second row
    row = Score(application_id=app.id, rubric_id=rub.id, items=out["items"], total=out["total"], covered=out["covered"], flags=out["flags"], scorer=out["scorer"], created_at=now)
    s.add(row)
    s.flush()
    record_audit(s, actor, "score.created", f"application:{app.id}", {"rubric": rub.id, "version": rub.version, "total": out["total"], "covered": out["covered"], "flags": len(out["flags"])})
    record_event(s, "score.created", "application", app.id, {"total": out["total"]})
    return row


def unscored(s: Session) -> list[Application]:
    out = []
    for app in s.scalars(select(Application).where(Application.stage == "applied").order_by(Application.id)):
        rub = rubric_service.latest(s, app.role_id, locked_only=True)
        if rub is not None and latest_score(s, app.id, rub.id) is None:
            out.append(app)
    return out


def quote_check(s: Session) -> dict:
    """Re-check every stored evidence quote against the stored redacted text. The number that matters is `invalid`, and it must be 0."""
    total = invalid = 0
    bad: list[dict] = []
    texts = {r.application_id: (r.redacted_text, [(f.start, f.end) for f in find_injection(r.redacted_text)]) for r in s.scalars(select(Resume)) if r.redacted_text}
    for sc in s.scalars(select(Score)):
        text, blocked = texts.get(sc.application_id, (None, []))
        for it in sc.items:
            if it.get("state") != "scored":
                continue
            for q in it.get("quotes", []):
                total += 1
                ok = text is not None and evidence.verify_quote(q.get("text"), text, blocked).ok and text[q["start"]:q["start"] + len(q["text"])] == q["text"]
                if not ok:
                    invalid += 1
                    bad.append({"score": sc.id, "criterion": it.get("criterion_id")})
    return {"quotes": total, "invalid": invalid, "valid_percent": 100.0 if total == 0 else round(100 * (total - invalid) / total, 2), "bad": bad[:20]}
