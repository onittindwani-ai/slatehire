"""Demo mode only. These routes return 404 when DEMO_MODE is off."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from slatehire import clock, demo
from slatehire.api.deps import db, demo_only, get_ctx, owner, writer
from slatehire.context import Ctx
from sendora_core.events import record_event

router = APIRouter(prefix="/api/demo", tags=["demo"], dependencies=[Depends(demo_only)])


@router.get("/state", summary="The demo clock")
def state(s: Session = Depends(db), ctx: Ctx = Depends(get_ctx)):
    return {"now": ctx.now(s).isoformat()}


@router.post("/reset", summary="Reset to the seed data and a fresh clock")
def reset(s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(owner)):
    try:
        return demo.reset(s, ctx)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/tick", summary="Run the jobs once, now: the next application email arrives and waiting applicants are scored")
def tick(s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    from slatehire.jobs import run_cycle

    return run_cycle(s, ctx)


class AdvanceIn(BaseModel):
    hours: float = Field(ge=0, le=24 * 30)


@router.post("/advance", summary="Move the demo clock forward")
def advance(b: AdvanceIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    return {"now": clock.advance(s, b.hours).isoformat()}


class StressIn(BaseModel):
    n: int = Field(ge=1, le=20000)


@router.post("/stress-candidates", summary="Add many fictional applications, to check that long tables stay fast")
def stress(b: StressIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(owner)):
    from sqlalchemy import select

    from slatehire.models import Application, Candidate, Role

    role = s.scalars(select(Role).order_by(Role.id)).first()
    base = s.scalar(select(__import__("sqlalchemy").func.max(Candidate.id))) or 0
    now = ctx.now(s)
    s.bulk_insert_mappings(Candidate, [{"id": base + i + 1, "code": f"L{base + i + 1:05d}", "full_name": f"Fictional Person {i}", "email": "", "phone": "", "school": "", "source": "load test", "created_at": now} for i in range(b.n)])
    s.bulk_insert_mappings(Application, [{"candidate_id": base + i + 1, "role_id": role.id, "stage": "applied", "history": [], "decision_note": "", "note": "", "created_at": now, "updated_at": now} for i in range(b.n)])
    record_event(s, "demo.stress", None, None, {"n": b.n})
    return {"added": b.n}
