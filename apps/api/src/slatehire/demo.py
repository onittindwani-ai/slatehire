"""Demo mode: reset to the seed data and move the clock. Fictional people, offline stand ins, nothing real is touched."""

from __future__ import annotations

from sqlalchemy.orm import Session

from slatehire import clock, world
from slatehire.datadir import data_dir
from sendora_core.db import Base


def reset(session: Session, ctx) -> dict:
    """Erase every table and load the fictional seed. Only while demo shortcuts are on (DEMO_MODE and no owner password): with a real owner
    password this is refused here too, whatever route or tool called it, so a real database is never emptied by the demo button."""
    if not ctx.settings.demo_shortcuts:
        raise PermissionError("The demo reset is only available in demo mode with no owner password set.")
    data_dir(ctx.settings.seed_dir)  # a missing data folder is a plain error BEFORE anything is erased
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
