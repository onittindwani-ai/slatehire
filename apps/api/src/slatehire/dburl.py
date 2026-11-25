"""Which database a command line tool (alembic) should open. Reads the same settings as the app, so `.env` counts, and never guesses."""

from __future__ import annotations

import os

from slatehire.config import Settings


def resolve_url(x_url: str | None = None, env_file: str | None = None) -> str:
    """`-x url=...` wins. Otherwise DATABASE_URL from the environment or the env file (ENV_FILE names another file than .env).
    If it is set nowhere, stop with a plain message instead of quietly using a local SQLite file."""
    if x_url:
        return x_url
    settings = Settings(_env_file=env_file or os.environ.get("ENV_FILE", ".env"))
    if "database_url" not in settings.model_fields_set:
        raise RuntimeError(
            "DATABASE_URL is not set. Put it in your environment or in the .env file (or pass -x url=...). "
            "Alembic will not guess a database, so a stray SQLite file is never created by mistake."
        )
    return settings.database_url
