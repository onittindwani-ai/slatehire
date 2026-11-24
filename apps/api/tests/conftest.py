import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "apps/api/src"), str(ROOT)]

from fastapi.testclient import TestClient  # noqa: E402

import slatehire.guards  # noqa: E402,F401
from slatehire.api.app import create_app  # noqa: E402
from slatehire.config import Settings  # noqa: E402
from slatehire.context import Ctx  # noqa: E402
from sendora_core import models as _core  # noqa: E402,F401
from sendora_core.db import Base, make_engine, make_session_factory  # noqa: E402

DATA = str(ROOT / "data")


@pytest.fixture(autouse=True)
def _no_key_from_the_shell(monkeypatch):
    """The developer's shell may hold a real ANTHROPIC_API_KEY. No test may use it: a test that needs a key sets one explicitly and points it at a local fake server."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
HOOK = "hook-secret-for-tests"


def make_settings(tmp_path, **kw) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 't.sqlite3'}", session_secret="test-secret-test-secret", seed_dir=DATA, export_dir=str(tmp_path / "exports"), application_webhook_secret=HOOK, _env_file=None, **kw)


def make_ctx(tmp_path, **kw) -> Ctx:
    s = make_settings(tmp_path, **kw)
    eng = make_engine(s.database_url)
    Base.metadata.create_all(eng)
    return Ctx(s, make_session_factory(eng))


@pytest.fixture()
def ctx(tmp_path):
    return make_ctx(tmp_path)


@pytest.fixture(scope="session")
def _world_db(tmp_path_factory):
    from slatehire import demo

    c = make_ctx(tmp_path_factory.mktemp("world"))
    with c.factory() as s:
        demo.reset(s, c)
    return c


@pytest.fixture()
def ro(_world_db):
    """The demo world, read only. Tests that write use `world`."""
    return _world_db


@pytest.fixture()
def world(tmp_path):
    from slatehire import demo

    c = make_ctx(tmp_path)
    with c.factory() as s:
        demo.reset(s, c)
    return c


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(make_settings(tmp_path)))


def login(client, email="owner@example.test"):
    r = client.post("/api/auth/login", json={"email": email, "password": "demo-password-1"})
    assert r.status_code == 200, r.text
    return {"x-session": r.json()["token"]}
