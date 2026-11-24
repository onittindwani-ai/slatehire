"""Alembic environment. The database URL comes from DATABASE_URL (or -x url=...), never from this file."""

import os

from alembic import context
from sqlalchemy import create_engine

import slatehire.models  # noqa: F401  registers tables
from sendora_core import models as _core  # noqa: F401
from sendora_core.db import Base

target_metadata = Base.metadata


def _url() -> str:
    return context.get_x_argument(as_dictionary=True).get("url") or os.environ.get("DATABASE_URL", "sqlite:///./slatehire.sqlite3")


def run_migrations_online() -> None:
    engine = create_engine(_url())
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=_url().startswith("sqlite"))
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
