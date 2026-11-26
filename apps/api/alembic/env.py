"""Alembic environment. The database URL is read the same way the app reads it: from the environment, or from the .env file (ENV_FILE to name another).

There is no silent fallback to a local SQLite file: if no DATABASE_URL is found anywhere, the command stops and says so.
`-x url=...` still overrides, for tests and one off runs.
"""

from alembic import context
from sqlalchemy import create_engine

import slatehire.models  # noqa: F401  registers tables
from slatehire.dburl import resolve_url
from sendora_core import models as _core  # noqa: F401
from sendora_core.db import Base

target_metadata = Base.metadata


def _url() -> str:
    return resolve_url(context.get_x_argument(as_dictionary=True).get("url"))


def run_migrations_online() -> None:
    url = _url()
    engine = create_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=url.startswith("sqlite"))
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
