from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from slatehire import rubric_service, scoring_service
from slatehire.attention import attention_of
from slatehire.models import Application, Candidate, Resume, Role


def iso(v: datetime | date | None) -> str | None:
    """SQLite hands back times without a zone. Every stored time is UTC, so say so: a browser would otherwise read it as local time."""
    if not v:
        return None
    if isinstance(v, datetime) and v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.isoformat()


def blind_enforced(s: Session, app: Application) -> bool:
    """Identity stays hidden until the shortlist decision when the role's locked rubric says so. The rubric signature covers that setting."""
    rub = rubric_service.latest(s, app.role_id, locked_only=True)
    return bool(rub and rub.blind and app.stage == "applied")


KNOWN_SOURCES = frozenset({"paste", "upload", "csv", "email", "webhook", "ashby", "workable", "greenhouse", "load test"})


def source_label(c: Candidate, hidden: bool) -> str:
    """Where the application came from. While identity is hidden only a known channel is shown: a CSV file can carry any text in this column ("Stanford career fair",
    "referral from Jo"), and free text is exactly what blind mode keeps from the first reader."""
    return c.source if not hidden or (c.source or "").lower() in KNOWN_SOURCES else "other"


def person(c: Candidate, hidden: bool) -> dict:
    if hidden:
        return {"code": c.code, "name": f"Candidate {c.code}", "email": None, "phone": None, "school": None, "source": source_label(c, True), "hidden": True}
    return {"code": c.code, "name": c.full_name, "email": c.email or None, "phone": c.phone or None, "school": c.school or None, "source": c.source, "hidden": False}


def row(s: Session, app: Application, c: Candidate, role: Role, rub_id: int | None, hidden: bool | None = None) -> dict:
    sc = scoring_service.latest_score(s, app.id, rub_id) if rub_id else None
    hide = blind_enforced(s, app) if hidden is None else hidden
    p = person(c, hide)
    return {"id": app.id, "code": c.code, "name": p["name"], "hidden": hide, "role": role.key, "role_title": role.title, "stage": app.stage, "total": sc.total if sc else None, "covered": sc.covered if sc else None,
            "flags": len(sc.flags) if sc else 0, "source": source_label(c, hide), "updated_at": iso(app.updated_at), "deleted": c.purged_at is not None,
            "attention": attention_of(app)}


def pieces(res: Resume | None, items: list[dict], reveal: bool) -> list[dict]:
    """The resume as pieces for the browser: plain text (with evidence highlights) and identity pieces. Original text is included only when `reveal` is true."""
    if res is None:
        return []
    marks: list[tuple[int, int, str]] = []
    for it in items:
        for q in it.get("quotes", []):
            marks.append((q["start"], q["start"] + len(q["text"]), it["criterion_id"]))
    out, pos = [], 0
    for g in res.segments:
        r = g["r"]
        if g["c"] is not None:
            out.append({"kind": "identity", "cat": g["c"], "text": r, **({"original": g["o"]} if reveal else {})})
        else:
            cuts = sorted({0, len(r), *[x for a, b, _c in marks for x in (a - pos, b - pos) if 0 < x < len(r)]})
            for a, b in zip(cuts, cuts[1:]):
                covers = [c for ma, mb, c in marks if ma <= pos + a and pos + b <= mb]
                out.append({"kind": "text", "text": r[a:b], "criteria": covers})
        pos += len(r)
    return out
