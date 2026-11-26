"""The fairness indicator. This is the ONLY module that reads voluntary demographic labels (a test enforces that). It counts people who reached each step, by group, and hands the counts to `fairness`.

An indicator for a person to look at. It is not a finding of discrimination and it is not legal advice. Nothing here infers a group for anyone: a person without a label is counted as undisclosed.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from fractions import Fraction

from sqlalchemy import select
from sqlalchemy.orm import Session

from slatehire import fairness
from slatehire.errors import RuleError, need_person
from slatehire.models import Application, Candidate, Demographic, FairnessAggregate, FairnessReport, Role
from slatehire.pipeline import reached
from sendora_core.audit import record_audit

THRESHOLD_SHAPE = re.compile(r"\d{1,6}(?:/\d{1,6}|\.\d{1,6})?")
DEFAULT_FLOOR = 10  # the same floor as FAIRNESS_MIN_GROUP; a session carries the real one (Ctx puts it in session.info)
QUARTER = re.compile(r"\d{4}-Q[1-4]")
LEGACY_MONTH = re.compile(r"(\d{4})-(\d{2})")
STEP_STAGE = {"shortlisted": "shortlisted", "interviewed": "interviewing", "offered": "offer", "hired": "hired"}
PREV = {"shortlisted": None, "interviewed": "shortlisted", "offered": "interviewing", "hired": "offer"}


def set_labels(s: Session, mapping: dict[str, str], actor: str) -> dict:
    """mapping: candidate code -> the label the person chose to give. Replaces an earlier label. Never guesses."""
    need_person(actor)
    codes = {c.code: c.id for c in s.scalars(select(Candidate)) if c.purged_at is None}  # a deleted person gets no new label
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


def _steps_of(app: Application) -> dict[str, tuple[int, int]]:
    """For each step, (entered, passed) of one person: 1 and 1 when they reached it, 1 and 0 when they were in the step before and went no further."""
    out: dict[str, tuple[int, int]] = {}
    for step, stage in STEP_STAGE.items():
        prev = PREV[step]
        if prev is None or reached(app, prev):
            out[step] = (1, 1 if reached(app, stage) else 0)
    return out


def quarter_of(when) -> str:
    """The quarter a date falls in ("2026-Q4"). Nothing finer is kept about when a deleted person left the counts."""
    return f"{when.year}-Q{(when.month - 1) // 3 + 1}"


def fold(s: Session, app: Application, now) -> bool:
    """Before a person's label is deleted with them, add what they contributed to the fairness counts to a running total: role, step, group label and quarter, nothing else (no name,
    no address, no day, no month). Without it every deletion would turn a labelled person into "undisclosed", and after a year of retention sweeps the report could compare nobody. Done once per
    application. People deleted before this release were not folded and keep counting as undisclosed. A group with fewer than the floor of people in a finished quarter is moved to
    "undisclosed" for that quarter (see seal_small_cells), so the totals never hold a cell that is one person's label."""
    if app.fairness_folded:
        return False
    row = s.get(Demographic, app.id)
    group = row.group_label if row is not None else fairness.UNDISCLOSED
    period = quarter_of(now)
    for step, (entered, passed) in _steps_of(app).items():
        agg = s.scalars(select(FairnessAggregate).where(FairnessAggregate.role_id == app.role_id, FairnessAggregate.step == step, FairnessAggregate.group_label == group, FairnessAggregate.month == period)).first()
        if agg is None:
            agg = FairnessAggregate(role_id=app.role_id, step=step, group_label=group, month=period, entered=0, passed=0, people=0)
            s.add(agg)
        agg.entered, agg.passed = agg.entered + entered, agg.passed + passed
        if step == "shortlisted":
            agg.people += 1  # every person is counted once, on the first step
    app.fairness_folded = True
    s.flush()
    if s.info.get("fairness_sealed") != period:  # once per session and quarter is enough: the sweep folds many people in one go
        seal_small_cells(s, now)
        s.info["fairness_sealed"] = period
    return True


def _merge_into(s: Session, row: FairnessAggregate, group: str, period: str) -> None:
    """Move one total to (group, period): into the total that is already there, or by renaming this one."""
    other = s.scalars(select(FairnessAggregate).where(FairnessAggregate.role_id == row.role_id, FairnessAggregate.step == row.step, FairnessAggregate.group_label == group, FairnessAggregate.month == period,
                                                      FairnessAggregate.id != row.id)).first()
    if other is None:
        row.group_label, row.month = group, period
        return
    other.entered, other.passed, other.people = other.entered + row.entered, other.passed + row.passed, other.people + row.people
    s.delete(row)


def seal_small_cells(s: Session, now=None, floor: int | None = None) -> int:
    """Keep the kept totals from being one person's label. (1) A total written with a month ("2026-11", from the first release of the totals) is moved to its quarter. (2) In every quarter that
    is over, a group with fewer than `floor` people (FAIRNESS_MIN_GROUP, the same floor the report uses for "too few") is moved to "undisclosed" for that role and quarter, with its counts: the report
    would not compare a group that small anyway, and a cell of one or two people next to the exact date in the audit entry of a deletion would give that person's label away. The quarter that
    is still open keeps its cells until it is over (a cell grows as people are deleted), which is the one stretch where a small cell can exist; docs/14 says so. Returns how many totals moved."""
    floor = floor or int(s.info.get("fairness_floor") or DEFAULT_FLOOR)
    current = quarter_of(now or datetime.now(UTC))
    moved = 0
    for row in list(s.scalars(select(FairnessAggregate).where(~FairnessAggregate.month.like("%-Q%")))):
        m = LEGACY_MONTH.fullmatch(row.month or "")
        if m and 1 <= int(m.group(2)) <= 12:
            _merge_into(s, row, row.group_label, f"{m.group(1)}-Q{(int(m.group(2)) - 1) // 3 + 1}")
            moved += 1
    s.flush()
    rows = [r for r in s.scalars(select(FairnessAggregate)) if QUARTER.fullmatch(r.month or "") and r.month < current and r.group_label != fairness.UNDISCLOSED]
    people: dict[tuple[int, str, str], int] = {}
    for r in rows:
        people[(r.role_id, r.month, r.group_label)] = people.get((r.role_id, r.month, r.group_label), 0) + r.people
    for r in rows:
        if people[(r.role_id, r.month, r.group_label)] < floor:
            _merge_into(s, r, fairness.UNDISCLOSED, r.month)
            moved += 1
    s.flush()
    return moved


def counts(s: Session, role_key: str | None) -> tuple[dict, dict]:
    """Counts from the people who are still here plus the totals kept from people who were deleted."""
    q = select(Application)
    agg_q = select(FairnessAggregate)
    if role_key and role_key != "all":
        role = s.scalars(select(Role).where(Role.key == role_key)).first()
        if role is None:
            raise RuleError("No such role.")
        q = q.where(Application.role_id == role.id)
        agg_q = agg_q.where(FairnessAggregate.role_id == role.id)
    labels = {d.application_id: d.group_label for d in s.scalars(select(Demographic))}
    out: dict[str, dict[str, list[int]]] = {st: {} for st in fairness.STAGES}
    people = 0
    for app in s.scalars(q):
        if app.fairness_folded:
            continue  # already in the totals below
        people += 1
        g = labels.get(app.id, fairness.UNDISCLOSED)
        for step, (entered, passed) in _steps_of(app).items():
            cell = out[step].setdefault(g, [0, 0])
            cell[0] += entered
            cell[1] += passed
    kept = 0
    for agg in s.scalars(agg_q):
        cell = out[agg.step].setdefault(agg.group_label, [0, 0])
        cell[0] += agg.entered
        cell[1] += agg.passed
        kept += agg.people
    return out, {"people": people + kept, "labelled": sum(1 for a in labels), "kept_from_deleted": kept}


def run(s: Session, actor: str, role_key: str | None, min_group: int, threshold: str = "4/5", floor: int = 2, now=None) -> FairnessReport:
    """`floor` is FAIRNESS_MIN_GROUP from the settings: a report can ask for a larger smallest group, never a smaller one, so nobody can shrink it to read a handful of people."""
    need_person(actor)
    if not 2 <= min_group <= 200:
        raise RuleError("The smallest group size is between 2 and 200.")
    min_group = max(min_group, floor)
    if not THRESHOLD_SHAPE.fullmatch(threshold.strip()):  # no exponents, no huge numbers: Fraction("1e999999999") would take the server minutes
        raise RuleError("The threshold is a fraction such as 4/5, or a decimal such as 0.8.")
    try:
        thr = Fraction(threshold.strip())
    except (ValueError, ZeroDivisionError) as exc:
        raise RuleError("The threshold is a fraction such as 4/5.") from exc
    if not 0 < thr < 1:
        raise RuleError("The threshold is between 0 and 1.")
    seal_small_cells(s, now)  # a report is always worked out from totals with no small cell in a finished quarter
    cnt, meta = counts(s, role_key)
    rep = fairness.to_json(fairness.report({st: {g: tuple(v) for g, v in grp.items()} for st, grp in cnt.items()}, min_group, thr))
    rep["meta"] = {**meta, "role": role_key or "all", "note": "Labels are voluntary. Anyone without a label is counted as undisclosed."}
    row = FairnessReport(role_key=role_key or "all", min_group=min_group, payload=rep, created_by=actor)
    s.add(row)
    s.flush()
    record_audit(s, actor, "fairness.report", f"report:{row.id}", {"role": row.role_key, "flagged": len(rep["flagged"])})
    return row
