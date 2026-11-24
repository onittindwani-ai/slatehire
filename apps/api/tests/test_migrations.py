"""Migrations go up and down on SQLite, and the models match the migrated schema (no drift)."""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

import slatehire.models  # noqa: F401
from sendora_core import models as _core  # noqa: F401
from sendora_core.db import Base

API = Path(__file__).resolve().parents[1]


def cfg(url: str) -> Config:
    c = Config(str(API / "alembic.ini"))
    c.set_main_option("script_location", str(API / "alembic"))
    c.cmd_opts = type("o", (), {"x": [f"url={url}"]})()
    return c


def run_cycle(url: str):
    engine = create_engine(url)
    command.upgrade(cfg(url), "head")
    tables = set(inspect(engine).get_table_names())
    expected = set(Base.metadata.tables)
    assert expected <= tables
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"models drifted from the migration: {diff}"
    command.downgrade(cfg(url), "base")
    left = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert left == set(), f"downgrade left tables: {left}"
    command.upgrade(cfg(url), "head")  # up again after down


def test_sqlite_up_down_up(tmp_path):
    run_cycle(f"sqlite:///{tmp_path / 'm.sqlite3'}")


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="set TEST_POSTGRES_URL to run the Postgres cycle")
def test_postgres_up_down_up():
    run_cycle(os.environ["TEST_POSTGRES_URL"])
