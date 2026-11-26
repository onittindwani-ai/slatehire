"""Round 3: the guards, the shared address note and the settings that start the app. Each test fails on the code before the fix."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _run(code: str, env_extra: dict | None = None) -> str:
    """Run a few lines in a fresh interpreter, so nothing a test imported earlier can make the answer look right."""
    import os

    env = {**os.environ, "PYTHONPATH": f"{ROOT / 'apps/api/src'}:{ROOT}", "ENV_FILE": "/nonexistent.env", **(env_extra or {})}
    p = subprocess.run([sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True, env=env, cwd=ROOT, timeout=120)
    assert p.returncode == 0, p.stderr[-800:]
    return p.stdout.strip()


def test_create_app_switches_the_guards_on_in_a_fresh_process(tmp_path):
    out = _run(f"""
        import sys
        from slatehire.config import Settings
        from slatehire.api.app import create_app
        before = "slatehire.guards" in sys.modules
        create_app(Settings(database_url="sqlite:///{tmp_path / 'a.sqlite3'}", demo_mode=True, session_secret="demo-secret-demo-secret", seed_dir="", _env_file=None))
        from slatehire import guards
        print(before, guards.installed())
    """)
    assert out.endswith("True"), out  # the module is active after create_app, whatever was imported before


def test_the_worker_setup_switches_the_guards_on_in_a_fresh_process(tmp_path):
    out = _run(f"""
        from slatehire import worker
        from slatehire.config import Settings
        import sys
        s = Settings(database_url="sqlite:///{tmp_path / 'w.sqlite3'}", demo_mode=True, session_secret="demo-secret-demo-secret", seed_dir="", _env_file=None)
        worker.setup(s)
        from slatehire import guards
        print(guards.installed())
    """)
    assert out == "True"


def test_installing_twice_does_not_stack_the_guard():
    from sqlalchemy import event

    from slatehire import guards
    from slatehire.models import Scorecard

    guards.install()
    guards.install()
    assert event.contains(Scorecard, "before_update", guards._never) and guards.installed()


def test_the_package_text_is_about_this_system():
    import slatehire

    assert "voice" not in slatehire.__doc__.lower() and "hiring" in slatehire.__doc__.lower()


# ---- "database is locked" on an approval or a hire: a request that reads, then writes, while another connection writes ----

def _two_connections(tmp_path, use_write_factory: bool):
    """Thread A reads and then writes inside one session; thread B writes and commits in between. Returns (A's error or None, B's error or None)."""
    import threading

    from sqlalchemy import select

    from conftest import make_ctx
    from slatehire.models import Role

    ctx = make_ctx(tmp_path)
    with ctx.factory() as s:
        s.add(Role(key="r1", title="First role"))
        s.commit()
    a_has_read, b_done = threading.Event(), threading.Event()
    errors: dict[str, Exception | None] = {"a": None, "b": None}
    a_factory = ctx.write_factory if use_write_factory else ctx.factory

    def a() -> None:
        try:
            with a_factory() as s:
                s.scalars(select(Role)).all()  # the read that starts the transaction
                a_has_read.set()
                b_done.wait(timeout=3)  # B tries to write now; with the write lock taken first it waits for A, otherwise it goes through
                s.add(Role(key="from-a", title="Written by A"))
                s.commit()
        except Exception as exc:  # noqa: BLE001
            errors["a"] = exc
            a_has_read.set()

    def b() -> None:
        a_has_read.wait(timeout=5)
        try:
            with ctx.write_factory() as s:
                s.add(Role(key="from-b", title="Written by B"))
                s.commit()
        except Exception as exc:  # noqa: BLE001
            errors["b"] = exc
        finally:
            b_done.set()

    ta, tb = threading.Thread(target=a), threading.Thread(target=b)
    ta.start(), tb.start()
    ta.join(20), tb.join(20)
    return errors["a"], errors["b"], ctx


def test_a_plain_session_that_reads_then_writes_is_refused_at_once_when_another_writer_got_in_between(tmp_path):
    err_a, _err_b, _ctx = _two_connections(tmp_path, use_write_factory=False)
    assert err_a is not None and "locked" in str(err_a).lower()  # the cause, written down: this is what stopped an approval in the browser run


def test_a_write_session_takes_the_write_lock_first_so_both_writers_finish(tmp_path):
    from sqlalchemy import select

    from slatehire.models import Role

    import threading  # noqa: F401

    err_a, err_b, ctx = _two_connections(tmp_path, use_write_factory=True)
    assert err_a is None and err_b is None
    with ctx.factory() as s:
        assert {r.key for r in s.scalars(select(Role))} == {"r1", "from-a", "from-b"}


def test_a_request_that_writes_gets_a_write_session_and_a_page_load_a_plain_one(tmp_path):
    from types import SimpleNamespace

    from conftest import make_ctx
    from slatehire.api.deps import db

    ctx = make_ctx(tmp_path)

    def session_for(method: str, path: str = "/api/x", query: dict | None = None):
        req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(ctx=ctx)), method=method, query_params=query or {}, url=SimpleNamespace(path=path))
        gen = db(req)
        return gen, next(gen)

    for method, expect in (("POST", "IMMEDIATE"), ("PUT", "IMMEDIATE"), ("DELETE", "IMMEDIATE"), ("GET", None)):
        gen, s = session_for(method)
        assert s.get_bind().get_execution_options().get("sqlite_begin") == expect, method
        gen.close()
    gen, s = session_for("GET", query={"reveal": "true"})  # a reveal is written to the audit log
    assert s.get_bind().get_execution_options().get("sqlite_begin") == "IMMEDIATE"
    gen.close()


def test_the_mailbox_and_the_ats_pull_let_go_of_the_write_lock_before_they_call_out():
    import inspect

    from slatehire import jobs
    from slatehire.api import routes_write

    mailbox = inspect.getsource(jobs.job_mailbox)
    assert mailbox.index("s.commit()") < mailbox.index("fetch_new")
    ats = inspect.getsource(routes_write.pull_ats)
    assert ats.index("s.commit()") < ats.index("list_applicants")


# ---- alembic and the settings file at the repository root ----

def test_the_settings_file_is_found_in_a_folder_above_the_one_alembic_runs_in(tmp_path, monkeypatch):
    from slatehire import dburl

    (tmp_path / "apps" / "api").mkdir(parents=True)
    (tmp_path / ".env").write_text("DATABASE_URL=sqlite:///./from-the-root-env.sqlite3\n")
    monkeypatch.chdir(tmp_path / "apps" / "api")
    monkeypatch.delenv("ENV_FILE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert dburl.resolve_url() == "sqlite:///./from-the-root-env.sqlite3"  # before: "DATABASE_URL is not set" although the file was there
    monkeypatch.setenv("ENV_FILE", str(tmp_path / "other.env"))
    (tmp_path / "other.env").write_text("DATABASE_URL=sqlite:///./other.sqlite3\n")
    assert dburl.resolve_url() == "sqlite:///./other.sqlite3"


def test_no_settings_anywhere_still_stops_with_a_message(tmp_path, monkeypatch):
    from slatehire import dburl

    (tmp_path / "work").mkdir()
    monkeypatch.chdir(tmp_path / "work")
    monkeypatch.delenv("ENV_FILE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import pytest

    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        dburl.resolve_url()


# ---- sign in behind a shared address ----

def test_a_browser_that_signed_in_before_is_not_held_up_by_a_strangers_bad_tries(tmp_path):
    from hardening_helpers import OWNER, PASSWORD, real_client

    c = real_client(tmp_path)
    first = c.post("/api/auth/login", json={"email": OWNER, "password": PASSWORD})
    assert first.status_code == 200 and first.json()["device"]
    device = first.json()["device"]
    codes = [c.post("/api/auth/login", json={"email": OWNER, "password": f"wrong-{i}"}).status_code for i in range(12)]
    assert 429 in codes  # the strangers (no note) run into the limit
    assert c.post("/api/auth/login", json={"email": OWNER, "password": PASSWORD}).status_code == 429  # a browser with no note waits
    ok = c.post("/api/auth/login", json={"email": OWNER, "password": PASSWORD}, headers={"x-device": device})
    assert ok.status_code == 200  # the one that signed in before does not
    other = c.post("/api/auth/login", json={"email": "pat@rivera.example.test", "password": PASSWORD}, headers={"x-device": device})
    assert other.status_code in (200, 429) and "device" not in c.post("/api/auth/login", json={"email": OWNER, "password": "nope"}, headers={"x-device": device}).text


def test_the_settings_page_warns_when_the_api_does_not_trust_the_forwarded_address(tmp_path):
    from hardening_helpers import OWNER, PASSWORD, real_client, sign_in

    c = real_client(tmp_path)
    h = sign_in(c)
    assert not [p for p in c.get("/api/settings", headers=h).json()["problems"] if "does not trust" in p]
    c.post("/api/auth/login", json={"email": OWNER, "password": "wrong-password-x"}, headers={"x-forwarded-for": "203.0.113.9"})  # the web app says the visitor is 203.0.113.9, the connection is from the test client
    assert any("does not trust" in p and "FORWARDED_ALLOW_IPS" in p for p in c.get("/api/settings", headers=sign_in(c)).json()["problems"])


def test_the_hosted_guides_say_how_to_set_the_forwarded_addresses_and_no_longer_ask_for_a_session_secret_on_the_web_app():
    docs = ROOT / "docs"
    for name in ("06-DEPLOY-VERCEL.md", "07-DEPLOY-RAILWAY.md", "08-DEPLOY-HETZNER.md"):
        assert "FORWARDED_ALLOW_IPS" in (docs / name).read_text(), name
    assert "SESSION_SECRET" not in (docs / "06-DEPLOY-VERCEL.md").read_text().replace("do not put `SESSION_SECRET` here", "")
    assert "SESSION_SECRET" not in (ROOT / "deploy" / "vercel" / "README.md").read_text()
    web = "".join(p.read_text() for p in (ROOT / "apps" / "web").rglob("*.ts*") if "node_modules" not in p.parts and ".next" not in p.parts and "e2e" not in p.parts and "playwright" not in p.name)
    assert "SESSION_SECRET" not in web  # the web app never reads it, so the guide must not ask for it
