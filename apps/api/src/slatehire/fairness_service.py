"""The fairness indicator. This is the ONLY module that reads voluntary demographic labels (a test enforces that). It counts people who reached each step, by group, and hands the counts to `fairness`.

An indicator for a person to look at. It is not a finding of discrimination and it is not legal advice. Nothing here infers a group for anyone: a person without a label is counted as undisclosed.
"""

from __future__ import annotations

from fractions import Fraction

from sqlalchemy import select
from sqlalchemy.orm import Session

from slatehire import fairness
from slatehire.errors import RuleError, need_person
from slatehire.models import Application, Candidate, Demographic, FairnessReport, Role
from slatehire.pipeline import reached
from sendora_core.audit import record_audit

STEP_STAGE = {"shortlisted": "shortlisted", "interviewed": "interviewing", "offered": "offer", "hired": "hired"}
PREV = {"shortlisted": None, "interviewed": "shortlisted", "offered": "interviewing", "hired": "offer"}


def set_labels(s: Session, mapping: dict[str, str], actor: str) -> dict:
    """mapping: candidate code -> the label the person chose to give. Replaces an earlier label. Never guesses."""
    need_person(actor)
    codes = {c.code: c.id for c in s.scalars(select(Candidate))}
    apps = {a.candidate_id: a.id for a in s.scalars(select(Application).order_by(Application.id))}
    done = unknown = 0
    for code, label in mapping.items():
        label = (label or "").strip()
        if code not in codes or codes[code] not in apps:
            unknown += 1
            continue
        if not label or len(label) > 60:
            raise RuleError("A label is 1 to 60 characters. Leave a person out instead of guessing.")
        row = s.get(Demographic, apps[codes[code]])
        if row is None:
            s.add(Demographic(application_id=apps[codes[code]], group_label=label))
        else:
            row.group_label = label
        done += 1
    s.flush()
    record_audit(s, actor, "fairness.labels_set", None, {"labels": done, "unknown_codes": unknown})
    return {"set": done, "unknown": unknown}


def labelled_count(s: Session) -> int:
    from sqlalchemy import func

    return int(s.scalar(select(func.count()).select_from(Demographic)) or 0)


def counts(s: Session, role_key: str | None) -> tuple[dict, dict]:
    q = select(Application)
    if role_key and role_key != "all":
        role = s.scalars(select(Role).where(Role.key == role_key)).first()
        if role is None:
            raise RuleError("No such role.")
        q = q.where(Application.role_id == role.id)
    labels = {d.application_id: d.group_label for d in s.scalars(select(Demographic))}
    out: dict[str, dict[str, list[int]]] = {st: {} for st in fairness.STAGES}
    people = 0
    for app in s.scalars(q):
        people += 1
        g = labels.get(app.id, fairness.UNDISCLOSED)
        for step, stage in STEP_STAGE.items():
            prev = PREV[step]
            entered = prev is None or reached(app, prev)
            if not entered:
                continue
            cell = out[step].setdefault(g, [0, 0])
            cell[0] += 1
            cell[1] += 1 if reached(app, stage) else 0
    return out, {"people": people, "labelled": sum(1 for a in labels)}


def run(s: Session, actor: str, role_key: str | None, min_group: int, threshold: str = "4/5") -> FairnessReport:
    need_person(actor)
    if not 2 <= min_group <= 200:
        raise RuleError("The smallest group size is between 2 and 200.")
    try:
        thr = Fraction(threshold)
    except (ValueError, ZeroDivisionError) as exc:
        raise RuleError("The threshold is a fraction such as 4/5.") from exc
    if not 0 < thr < 1:
        raise RuleError("The threshold is between 0 and 1.")
    cnt, meta = counts(s, role_key)
    rep = fairness.to_json(fairness.report({st: {g: tuple(v) for g, v in grp.items()} for st, grp in cnt.items()}, min_group, thr))
    rep["meta"] = {**meta, "role": role_key or "all", "note": "Labels are voluntary. Anyone without a label is counted as undisclosed."}
    row = FairnessReport(role_key=role_key or "all", min_group=min_group, payload=rep, created_by=actor)
    s.add(row)
    s.flush()
    record_audit(s, actor, "fairness.report", f"report:{row.id}", {"role": row.role_key, "flagged": len(rep["flagged"])})
    return row
