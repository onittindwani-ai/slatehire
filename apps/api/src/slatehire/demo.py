"""Demo mode: reset to the seed data and move the clock. Fictional people, offline stand ins, nothing real is touched."""

from __future__ import annotations

from sqlalchemy.orm import Session

from slatehire import clock, world
from sendora_core.db import Base


def reset(session: Session, ctx) -> dict:
    session.rollback()
    session.close()
    with ctx.factory() as s:
        for table in reversed(Base.metadata.sorted_tables):  # empty the tables in place: a page that polls during a reset never meets a missing table
            s.execute(table.delete())
        s.flush()
        clock.set_offset(s, 0.0)
        s.flush()
        info = world.load_world(s, ctx)
        s.commit()
        return {"seed": info}
