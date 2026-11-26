"""Which database a command line tool (alembic) should open. Reads the same settings as the app, so `.env` counts, and never guesses."""

from __future__ import annotations

import os
from pathlib import Path

from slatehire.config import Settings


def find_env_file(start: Path | None = None) -> str:
    """The settings file the app would read when started from here: ENV_FILE if it is set, otherwise the first `.env` in this folder or in a folder above it (alembic runs in apps/api,
    and the file sits at the root of the repository). If there is none the plain name is returned, and the settings then come from the environment alone."""
    if os.environ.get("ENV_FILE"):
        return os.environ["ENV_FILE"]
    here = (start or Path.cwd()).resolve()
    for folder in (here, *list(here.parents)[:4]):
        if (folder / ".env").is_file():
            return str(folder / ".env")
    return ".env"


def resolve_url(x_url: str | None = None, env_file: str | None = None) -> str:
    """`-x url=...` wins. Otherwise DATABASE_URL from the environment or the env file (ENV_FILE names another file than .env).
    If it is set nowhere, stop with a plain message instead of quietly using a local SQLite file."""
    if x_url:
        return x_url
    settings = Settings(_env_file=env_file or find_env_file())
    if "database_url" not in settings.model_fields_set:
        raise RuntimeError(
            "DATABASE_URL is not set. Put it in your environment or in the .env file (or pass -x url=...). "
            "Alembic will not guess a database, so a stray SQLite file is never created by mistake."
        )
    return settings.database_url
