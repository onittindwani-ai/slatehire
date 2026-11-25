"""The worker process: queues the recurring jobs and runs them. Start it with `python -m slatehire.worker`."""

from __future__ import annotations

import logging
import os
import signal
import time

from slatehire import guards
from slatehire.config import Settings
from slatehire.context import Ctx
from slatehire.dbsetup import make_private_engine
from slatehire.dbupgrade import add_missing_columns
from slatehire.jobs import make_handlers, schedule_due
from sendora_core.db import Base, make_session_factory, session_scope
from sendora_core.jobs import Worker

log = logging.getLogger("slatehire.worker")


def run_once(ctx: Ctx, worker: Worker) -> int:
    with session_scope(ctx.write_factory) as s:
        schedule_due(s, ctx)
    return worker.drain(limit=50)


def load_settings() -> Settings:
    """The worker reads the same environment file as the API (ENV_FILE, default .env), so the two never run on different settings."""
    return Settings(_env_file=os.environ.get("ENV_FILE", ".env"))


def setup(settings: Settings | None = None) -> tuple[Settings, Ctx, Worker]:
    """Everything the worker needs before its loop: the guards, the settings check, the database and the job handlers. Split from main() so a test can start it without the loop."""
    guards.install()  # the append only and locked rubric rules must hold in the worker as well as in the API
    settings = settings or load_settings()
    settings.check_runtime()  # same refusal as the API: an example secret, a demo on a server database, a placeholder identity on a live install
    engine = make_private_engine(settings.database_url)
    import slatehire.models  # noqa: F401
    from sendora_core import models as _c  # noqa: F401

    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
        add_missing_columns(engine)
    ctx = Ctx(settings, make_session_factory(engine))
    return settings, ctx, Worker(ctx.write_factory, make_handlers(ctx))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings, ctx, worker = setup()
    stop = {"now": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(now=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(now=True))
    log.info("worker started: mode=%s demo=%s", settings.mode.value, settings.demo_shortcuts)
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
