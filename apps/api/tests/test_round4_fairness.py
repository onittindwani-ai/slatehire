"""Round 4, the kept fairness totals: a quarter, never a month, and no small cell in a finished quarter. Each test fails on the code before the fix."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from hardening_helpers import real_ctx
from slatehire import fairness, fairness_service
from slatehire.models import FairnessAggregate, Role
from test_round3_people import _person

Q1 = datetime(2026, 1, 15, 9, 30, tzinfo=UTC)
Q3 = datetime(2026, 8, 3, tzinfo=UTC)
NOW = datetime(2026, 11, 20, tzinfo=UTC)  # the fourth quarter is open


def role_with(s, n_big: int, n_small: int, when, big="Group A", small="Group B"):
    role = Role(key="r", title="R")
    s.add(role)
    s.flush()
    n = 0
    for group, count in ((big, n_big), (small, n_small)):
        for i in range(count):
            n += 1
            app = _person(s, role, n, group, selected=i % 2 == 0, declined=i % 2 == 1)
            fairness_service.fold(s, app, when)
    s.commit()
    return role


def rows(s):
    return list(s.scalars(select(FairnessAggregate)))


def test_a_kept_total_is_kept_by_quarter_and_never_by_month_or_day(tmp_path):
    ctx = real_ctx(tmp_path)
    with ctx.factory() as s:
        role_with(s, 12, 12, datetime(2026, 11, 20, tzinfo=UTC))
        assert {r.month for r in rows(s)} == {"2026-Q4"}
    assert fairness_service.quarter_of(datetime(2026, 3, 31)) == "2026-Q1" and fairness_service.quarter_of(datetime(2026, 4, 1)) == "2026-Q2" and fairness_service.quarter_of(datetime(2026, 12, 31)) == "2026-Q4"


def test_a_group_below_the_floor_in_a_finished_quarter_becomes_undisclosed_with_its_counts_kept(tmp_path):
    ctx = real_ctx(tmp_path)  # the floor is FAIRNESS_MIN_GROUP, 10
    with ctx.factory() as s:
        role_with(s, 12, 1, Q1)  # twelve people with one label and one person with another, all in the first quarter
        assert any(r.group_label == "Group B" for r in rows(s))  # while the quarter is open the cell exists
        before, meta0 = fairness_service.counts(s, None)
        fairness_service.seal_small_cells(s, NOW)  # the quarter is over
        s.commit()
        labels = {(r.month, r.group_label) for r in rows(s)}
        assert labels == {("2026-Q1", "Group A"), ("2026-Q1", fairness.UNDISCLOSED)}  # nobody's label is kept as a cell of one
        after, meta1 = fairness_service.counts(s, None)
        assert meta1["people"] == meta0["people"] == 13
        assert after["shortlisted"][fairness.UNDISCLOSED] == before["shortlisted"]["Group B"] and after["shortlisted"]["Group A"] == before["shortlisted"]["Group A"]  # the counts moved, none was lost


def test_the_quarter_that_is_still_open_keeps_its_cells_so_they_can_grow(tmp_path):
    ctx = real_ctx(tmp_path)
    with ctx.factory() as s:
        role_with(s, 12, 1, Q1)
        assert fairness_service.seal_small_cells(s, Q3) >= 1  # the first quarter is over in August
        role_with_b = s.scalars(select(Role)).first()
        app = _person(s, role_with_b, 99, "Group C", selected=True, declined=False)
        fairness_service.fold(s, app, NOW)
        s.commit()
        assert ("2026-Q4", "Group C") in {(r.month, r.group_label) for r in rows(s)}
        fairness_service.seal_small_cells(s, NOW)
        assert ("2026-Q4", "Group C") in {(r.month, r.group_label) for r in rows(s)}  # the fourth quarter is open


def test_a_fold_seals_the_quarters_that_ended_before_it(tmp_path):
    ctx = real_ctx(tmp_path)
    with ctx.factory() as s:
        role = role_with(s, 12, 1, Q1)
        app = _person(s, role, 99, "Group A", selected=True, declined=False)
        fairness_service.fold(s, app, NOW)  # a deletion in the fourth quarter closes the books on the first
        s.commit()
        assert not any(r.group_label == "Group B" for r in rows(s))


def test_totals_written_with_a_month_by_the_first_release_are_moved_to_their_quarter_and_merged(tmp_path):
    ctx = real_ctx(tmp_path)
    with ctx.factory() as s:
        role = Role(key="r", title="R")
        s.add(role)
        s.flush()
        for month, people in (("2026-01", 6), ("2026-02", 7), ("2026-11", 11)):
            s.add(FairnessAggregate(role_id=role.id, step="shortlisted", group_label="Group A", month=month, entered=people, passed=people // 2, people=people))
        s.commit()
        fairness_service.seal_small_cells(s, NOW)
        s.commit()
        got = {r.month: (r.entered, r.passed, r.people) for r in rows(s)}
        assert got == {"2026-Q1": (13, 6, 13), "2026-Q4": (11, 5, 11)}  # January and February became one quarter, nothing was added or lost


def test_the_report_is_worked_out_from_totals_with_no_small_cell_and_says_undisclosed_for_it(tmp_path):
    ctx = real_ctx(tmp_path)
    with ctx.factory() as s:
        role_with(s, 12, 1, Q1)
        rep = fairness_service.run(s, "owner@x.test", None, 10, now=NOW).payload
        groups = rep["stages"]["shortlisted"]["groups"]
        assert "Group B" not in groups and groups[fairness.UNDISCLOSED]["status"] == "undisclosed"
        assert s.scalar(select(func.count()).select_from(FairnessAggregate).where(FairnessAggregate.group_label == "Group B")) == 0
