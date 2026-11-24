"""Events and metrics. Every meaningful change writes an event, and the dashboards read counts from here."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sendora_core.models import Event, Metric


def record_event(
    session: Session, kind: str, entity_type: str | None = None, entity_id: str | int | None = None,
    payload: dict | None = None, request_id: str | None = None,
) -> Event:
    from sendora_core.redaction import redact_obj

    e = Event(
        kind=kind, entity_type=entity_type, entity_id=None if entity_id is None else str(entity_id),
        payload=redact_obj(payload or {}), request_id=request_id,
    )
    session.add(e)
    session.flush()
    return e


def recent_events(session: Session, after_id: int = 0, limit: int = 100, kind_prefix: str | None = None) -> list[Event]:
    q = select(Event).where(Event.id > after_id).order_by(Event.id).limit(limit)
    if kind_prefix:
        q = q.where(Event.kind.startswith(kind_prefix))
    return list(session.scalars(q))


def record_metric(session: Session, name: str, value: float, labels: dict | None = None) -> Metric:
    m = Metric(name=name, value=value, labels=labels or {})
    session.add(m)
    session.flush()
    return m


def metric_total(session: Session, name: str, since: datetime | None = None) -> float:
    q = select(func.coalesce(func.sum(Metric.value), 0.0)).where(Metric.name == name)
    if since:
        q = q.where(Metric.created_at >= since)
    return float(session.scalar(q) or 0.0)


def event_count(session: Session, kind: str) -> int:
    return int(session.scalar(select(func.count()).select_from(Event).where(Event.kind == kind)) or 0)
