"""Score an application against the locked rubric of its role. Input is the redacted resume only. The score is an aid for a person, never a decision."""

from __future__ import annotations

import json

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from slatehire import evidence, rubric_service, scoring
from slatehire.attention import LANGUAGE_PREFIX, MISSING_PREFIX, REASON, attention_of
from slatehire.errors import RuleError
from slatehire.models import Application, Resume, Score, State
from slatehire.redaction import PLACEHOLDER_RE  # noqa: F401  (kept so a reader sees what the scorer never receives)
from slatehire.untrusted import INJECTION_SCAN, entries, find_injection
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
    kind = attention_of(app)
    if kind:  # a resume nobody could read, or one the scorer cannot read: a person goes first
        raise RuleError(REASON[kind])
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


def _unscored_query(rid: int, rubric_id: int):
    """The applicants of one role still waiting for a score under its locked rubric, in one query: not one per applicant."""
    return (select(Application).where(Application.stage == "applied", Application.role_id == rid, ~Application.note.like(f"{MISSING_PREFIX}%"), ~Application.note.like(f"{LANGUAGE_PREFIX}%"),
                                      ~exists().where(Score.application_id == Application.id, Score.rubric_id == rubric_id)).order_by(Application.id))


def _locked_rubric_ids(s: Session) -> dict[int, int]:
    from slatehire.models import Role

    out = {}
    for rid in s.scalars(select(Role.id)):
        rub = rubric_service.latest(s, rid, locked_only=True)
        if rub is not None:
            out[rid] = rub.id
    return out


def unscored(s: Session) -> list[Application]:
    """Applicants who wait for a score. A resume nobody could read, and one that is not in English, are left for a person: a score of nothing would put them at the bottom of the list."""
    out: list[Application] = []
    for rid, rubric_id in _locked_rubric_ids(s).items():
        out.extend(s.scalars(_unscored_query(rid, rubric_id)))
    return sorted(out, key=lambda a: a.id)


def count_unscored(s: Session) -> int:
    return sum(int(s.scalar(select(func.count()).select_from(_unscored_query(rid, rubric_id).order_by(None).subquery())) or 0) for rid, rubric_id in _locked_rubric_ids(s).items())


BATCH = 400  # resumes and scores are read this many at a time, so the check holds a small part of the data in memory whatever its size


def _blocked(res: Resume) -> list[tuple[int, int]]:
    """Where the lines that talk to the scorer are in the stored redacted text. Read from the resume when the scan was stored with it; an older row is scanned once and stored."""
    if (res.injection_scan or 0) < INJECTION_SCAN:
        res.injection = entries(res.redacted_text or "", find_injection(res.redacted_text or ""))
        res.injection_scan = INJECTION_SCAN
    return [(int(e["start"]), int(e["end"])) for e in res.injection]


def quote_check(s: Session) -> dict:
    """Re-check every stored evidence quote against the stored redacted text. The number that matters is `invalid`, and it must be 0.
    Read in batches, and the places of the flagged lines are read from the resume, not searched for again."""
    total = invalid = 0
    bad: list[dict] = []
    last = 0
    while True:
        scores = list(s.scalars(select(Score).where(Score.id > last).order_by(Score.id).limit(BATCH)))
        if not scores:
            break
        last = scores[-1].id
        texts = {r.application_id: r for r in s.scalars(select(Resume).where(Resume.application_id.in_({sc.application_id for sc in scores})))}
        for sc in scores:
            res = texts.get(sc.application_id)
            text = res.redacted_text if res is not None and res.redacted_text else None
            blocked = _blocked(res) if text is not None else []
            for it in sc.items:
                if it.get("state") != "scored":
                    continue
                for q in it.get("quotes", []):
                    total += 1
                    ok = text is not None and evidence.verify_quote(q.get("text"), text, blocked).ok and text[q["start"]:q["start"] + len(q["text"])] == q["text"]
                    if not ok:
                        invalid += 1
                        bad.append({"score": sc.id, "criterion": it.get("criterion_id")})
        s.flush()  # a backfilled scan is saved, then these rows are let go of
        for obj in [*scores, *texts.values()]:
            s.expunge(obj)
    return {"quotes": total, "invalid": invalid, "valid_percent": 100.0 if total == 0 else round(100 * (total - invalid) / total, 2), "bad": bad[:20]}


CACHE_KEY = "quote_check_cache"


def quote_summary(s: Session) -> dict:
    """The quote check for the page that loads on every screen. It is worked out again only when a score or a resume was added or removed since last time."""
    mark = f"{s.scalar(select(func.count()).select_from(Score))}:{s.scalar(select(func.max(Score.id)))}:{s.scalar(select(func.count()).select_from(Resume))}:{s.scalar(select(func.max(Resume.id)))}"
    row = s.get(State, CACHE_KEY)
    if row is not None:
        try:
            cached = json.loads(row.value)
            if cached.get("mark") == mark:
                return cached["result"]
        except (ValueError, KeyError):
            pass
    result = quote_check(s)
    if row is None:
        s.add(State(key=CACHE_KEY, value=json.dumps({"mark": mark, "result": result})))
    else:
        row.value = json.dumps({"mark": mark, "result": result})
    return result
