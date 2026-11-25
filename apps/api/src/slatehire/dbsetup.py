"""The database engine the app and the worker use: the shared engine, with two safety settings added.

1. Error messages never carry the values of a failed statement. Without this, one rejected insert printed the applicant's name, email and
   resume text into the worker's log and into `docker logs`.
2. On SQLite, savepoints work as they do on Postgres (the standard recipe from the SQLAlchemy documentation), so one bad email or applicant can be rolled
   back on its own without losing the rest of the batch.
3. On SQLite, a session that can write starts with BEGIN IMMEDIATE (`write_factory`), which takes the write lock first. A plain transaction only reads at first and asks for the write lock
   at its first write; when another connection has written in between, SQLite refuses at once with "database is locked" whatever the 30 second wait is, because the snapshot the first
   read took is out of date. That is what stopped an approval or a hire while the worker or a page load wrote. Reads (GET requests) use the plain factory and are never held up by a writer.
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from sendora_core.db import make_engine

IMMEDIATE = "IMMEDIATE"


def write_factory(factory: sessionmaker[Session]) -> sessionmaker[Session]:
    """The factory for requests and jobs that can write. On SQLite it begins with BEGIN IMMEDIATE; on Postgres (which has row locks and no such conflict) it is the same factory."""
    bind = factory.kw.get("bind")
    if bind is None or bind.dialect.name != "sqlite":
        return factory
    return sessionmaker(**{**factory.kw, "bind": bind.execution_options(sqlite_begin=IMMEDIATE)})


def make_private_engine(url: str) -> Engine:
    engine = make_engine(url)
    engine.hide_parameters = True
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _own_transactions(dbapi_conn, _):  # pragma: no cover - driver hook
            dbapi_conn.isolation_level = None  # the driver stops guessing when a transaction starts

        @event.listens_for(engine, "begin")
        def _begin(conn):  # pragma: no cover - driver hook
            conn.exec_driver_sql("BEGIN IMMEDIATE" if conn.get_execution_options().get("sqlite_begin") == IMMEDIATE else "BEGIN")

    return engine
