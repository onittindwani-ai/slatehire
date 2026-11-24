"""The worker process: queues the recurring jobs and runs them. Start it with `python -m slatehire.worker`."""

from __future__ import annotations

import logging
import signal
import time

from slatehire.config import Settings
from slatehire.context import Ctx
from slatehire.jobs import make_handlers, schedule_due
from sendora_core.db import Base, make_engine, make_session_factory, session_scope
from sendora_core.jobs import Worker

log = logging.getLogger("slatehire.worker")


def run_once(ctx: Ctx, worker: Worker) -> int:
    with session_scope(ctx.factory) as s:
        schedule_due(s, ctx)
    return worker.drain(limit=50)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings()
    engine = make_engine(settings.database_url)
    import slatehire.models  # noqa: F401
    from sendora_core import models as _c  # noqa: F401

    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    ctx = Ctx(settings, make_session_factory(engine))
    worker = Worker(ctx.factory, make_handlers(ctx))
    stop = {"now": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(now=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(now=True))
    log.info("worker started: mode=%s demo=%s", settings.mode.value, settings.demo_mode)
    while not stop["now"]:
        try:
            n = run_once(ctx, worker)
            if n:
                log.info("ran %d job(s)", n)
        except Exception:  # never let one bad loop stop the worker
            log.exception("worker loop error")
        time.sleep(2)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
