"""Columns added after the first release, for the SQLite zero setup path. `create_all` makes missing tables but never adds a column to a table that already exists, so a
database file made by an older version would fail with "no such column". Postgres installs use `alembic upgrade head` instead (migration 0002)."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

ADDED_COLUMNS = (("cf_resume", "injection_scan", "INTEGER NOT NULL DEFAULT 0"), ("cf_resume", "language", "VARCHAR(10) NOT NULL DEFAULT 'en'"))


def add_missing_columns(engine: Engine) -> list[str]:
    """Add every column in ADDED_COLUMNS that an existing SQLite table lacks. Returns what it added. Does nothing on other databases."""
    if engine.dialect.name != "sqlite":
        return []
    added: list[str] = []
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, column, ddl in ADDED_COLUMNS:
            if insp.has_table(table) and column not in {c["name"] for c in insp.get_columns(table)}:
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl}'))
                added.append(f"{table}.{column}")
    return added
