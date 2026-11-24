"""The clock. In demo mode time starts at a fixed seed date (so numbers and screenshots repeat) plus a stored offset the demo bar moves.

Outside demo mode the offset is ignored and the real time is used.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from slatehire.models import State

DEMO_START = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)  # a Tuesday morning


def now(session: Session, demo_mode: bool) -> datetime:
    if not demo_mode:
        return datetime.now(UTC)
    row = session.get(State, "clock_offset_hours")
    return DEMO_START + timedelta(hours=float(row.value) if row and row.value else 0.0)


def today(session: Session, demo_mode: bool) -> date:
    return now(session, demo_mode).date()


def set_offset(session: Session, hours: float) -> None:
    row = session.get(State, "clock_offset_hours")
    if row is None:
        session.add(State(key="clock_offset_hours", value=str(hours)))
    else:
        row.value = str(hours)


def advance(session: Session, hours: float) -> datetime:
    row = session.get(State, "clock_offset_hours")
    cur = float(row.value) if row and row.value else 0.0
    set_offset(session, cur + hours)
    session.flush()
    return now(session, True)
