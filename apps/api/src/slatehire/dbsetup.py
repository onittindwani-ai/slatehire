"""The database engine the app and the worker use: the shared engine, with two safety settings added.

1. Error messages never carry the values of a failed statement. Without this, one rejected insert printed the applicant's name, email and
   resume text into the worker's log and into `docker logs`.
2. On SQLite, savepoints work as they do on Postgres (the standard recipe from the SQLAlchemy documentation), so one bad email or applicant can be rolled
   back on its own without losing the rest of the batch.
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.engine import Engine

from sendora_core.db import make_engine


def make_private_engine(url: str) -> Engine:
    engine = make_engine(url)
    engine.hide_parameters = True
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _own_transactions(dbapi_conn, _):  # pragma: no cover - driver hook
            dbapi_conn.isolation_level = None  # the driver stops guessing when a transaction starts

        @event.listens_for(engine, "begin")
        def _begin(conn):  # pragma: no cover - driver hook
            conn.exec_driver_sql("BEGIN")

    return engine
