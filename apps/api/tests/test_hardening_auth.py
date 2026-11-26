"""Sign in, demo shortcuts, the refusal to start on unsafe settings, and the worker reading the same settings as the API."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import make_settings
from hardening_helpers import APPROVER, OWNER, PASSWORD, REAL_SECRET, real_client, real_ctx, real_settings, sign_in
from slatehire import clock, demo, worker
from slatehire.api import routes_auth
from slatehire.api.app import create_app
from slatehire.config import Settings
from slatehire.models import Role
from sendora_core.settings import ConfigError

DEMO_ACCOUNTS = ("approver@example.test", "iris.wells@example.test", "jonas.okafor@example.test", "viewer@example.test", "owner@example.test")


def example_owner_settings(tmp_path, **kw) -> Settings:
    return real_settings(tmp_path, owner_email="owner@example.test", company_name="Example Company", **kw)


# ---- sign in ----

def test_login_key_ignores_spaces_and_capitals(tmp_path):
    c = real_client(tmp_path)
    variants = [OWNER, f" {OWNER}", f"{OWNER} ", OWNER.upper(), f"\t{OWNER}", f"{OWNER}\n"]
    codes = [c.post("/api/auth/login", json={"email": v, "password": "wrong-password"}).status_code for v in variants]
    assert codes[:5] == [401] * 5 and codes[5] == 429  # the sixth try is refused whatever padding it uses


def test_login_accepts_a_padded_email_with_the_right_password(tmp_path):
    c = real_client(tmp_path)
    r = c.post("/api/auth/login", json={"email": f"  {OWNER.title()} ", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["user"] == OWNER


def test_login_refuses_oversize_fields(tmp_path):
    c = real_client(tmp_path)
    assert c.post("/api/auth/login", json={"email": "a" * 300 + "@x.test", "password": "x"}).status_code == 422
    assert c.post("/api/auth/login", json={"email": OWNER, "password": "x" * 2000}).status_code == 422


def test_each_address_has_its_own_wider_limit(tmp_path):
    c = real_client(tmp_path, login_burst=2)
    codes = [c.post("/api/auth/login", json={"email": f"user{i}@x.test", "password": "x"}).status_code for i in range(40)]
    assert codes[0] == 401 and 429 in codes[30:]  # a new email every time never gets a fresh set of tries


def test_guesses_spread_over_many_addresses_still_run_out(tmp_path):
    app = create_app(real_settings(tmp_path, login_burst=2))
    codes = []
    for i in range(30):
        c = TestClient(app, base_url="http://api.test", client=(f"203.0.113.{i + 1}", 50000 + i))  # a different visitor each time
        codes.append(c.post("/api/auth/login", json={"email": OWNER, "password": "wrong-password"}).status_code)
    assert codes[0] == 401 and 429 in codes[20:]
    other = TestClient(app, base_url="http://api.test", client=("198.51.100.5", 40000))
    assert other.post("/api/auth/login", json={"email": "someone.else@x.test", "password": "x"}).status_code == 401  # other accounts are not affected


def test_unknown_accounts_cost_the_same_work_as_wrong_passwords(tmp_path, monkeypatch):
    calls = []
    real = routes_auth.verify_password_or_dummy
    monkeypatch.setattr(routes_auth, "verify_password_or_dummy", lambda pw, h: (calls.append(h), real(pw, h))[1])
    c = real_client(tmp_path)
    assert c.post("/api/auth/login", json={"email": "nobody@x.test", "password": "x"}).status_code == 401
    assert calls == [None]  # a hash check against a throw away hash was still done


# ---- demo shortcuts ----

def test_a_real_owner_password_switches_every_demo_shortcut_off_even_in_demo_mode(tmp_path):
    s = real_settings(tmp_path, demo_mode=True, approver_email=None, approver_password_hash=None, members_json="")
    assert s.demo_shortcuts is False
    c = TestClient(create_app(s), base_url="http://api.test")
    for email in DEMO_ACCOUNTS:
        assert c.post("/api/auth/login", json={"email": email, "password": "demo-password-1"}).status_code == 401, email
    h = sign_in(c)
    assert c.get("/api/auth/me", headers=h).json()["demo_mode"] is False
    for path, body in (("/api/demo/reset", None), ("/api/demo/tick", None), ("/api/demo/advance", {"hours": 1}), ("/api/demo/stress-candidates", {"n": 1})):
        assert c.post(path, headers=h, json=body).status_code == 404, path
    assert c.get("/api/demo/state", headers=h).status_code == 404


def test_an_approver_with_no_password_hash_cannot_sign_in_with_the_public_password(tmp_path):
    s = real_settings(tmp_path, demo_mode=True, approver_password_hash=None)  # a half set up approver next to a real owner password
    c = TestClient(create_app(s), base_url="http://api.test")
    assert c.post("/api/auth/login", json={"email": APPROVER, "password": "demo-password-1"}).status_code == 401


def test_the_demo_reset_function_refuses_on_its_own_when_an_owner_password_is_set(tmp_path):
    ctx = real_ctx(tmp_path, demo_mode=True)
    with ctx.factory() as s:
        s.add(Role(key="keep", title="Keep this role"))
        s.commit()
    with ctx.factory() as s, pytest.raises(PermissionError, match="owner password"):
        demo.reset(s, ctx)  # a script or a tool calling it directly is stopped too, not only the route
    with ctx.factory() as s:
        assert s.scalars(select(Role).where(Role.key == "keep")).first() is not None


def test_demo_accounts_and_the_clock_exist_while_demo_shortcuts_are_on(tmp_path):
    c = TestClient(create_app(make_settings(tmp_path)))
    for email in ("approver@example.test", "iris.wells@example.test", "jonas.okafor@example.test", "viewer@example.test", "owner@example.test"):
        assert c.post("/api/auth/login", json={"email": email, "password": "demo-password-1"}).status_code == 200, email
    h = sign_in(c, "owner@example.test", "demo-password-1")
    assert c.get("/api/auth/me", headers=h).json()["demo_mode"] is True and c.get("/api/demo/state", headers=h).status_code == 200


def test_outside_the_demo_the_clock_is_the_real_one(tmp_path):
    ctx = real_ctx(tmp_path, demo_mode=True)  # demo mode on, owner password set: not a demo
    with ctx.factory() as s:
        assert abs((ctx.now(s) - datetime.now(UTC)).total_seconds()) < 5 and ctx.now(s) != clock.DEMO_START


# ---- refusal to start ----

def test_the_api_refuses_an_example_secret_outside_the_demo(tmp_path):
    with pytest.raises(ConfigError, match="SESSION_SECRET"):
        create_app(real_settings(tmp_path, session_secret="change-me-to-a-long-random-string"))


def test_a_live_start_is_refused_while_the_company_or_the_owner_is_a_placeholder(tmp_path):
    with pytest.raises(ConfigError, match="COMPANY_NAME"):
        create_app(real_settings(tmp_path, mode="live", company_name="Example Company"))
    with pytest.raises(ConfigError, match="OWNER_EMAIL"):
        create_app(real_settings(tmp_path, mode="live", owner_email="owner@example.test"))
    assert create_app(real_settings(tmp_path, mode="live")).version == "1.0.2"  # real names: it starts
    assert create_app(real_settings(tmp_path, mode="draft", company_name="Example Company")).version  # draft may start, and problems() lists it
    assert any("COMPANY_NAME" in p for p in real_settings(tmp_path, company_name="Example Company").problems())


def test_a_live_demo_may_keep_the_example_identity(tmp_path):
    s = make_settings(tmp_path, mode="live")  # the browser tests run MODE=live DEMO_MODE=true
    assert s.runtime_errors() == []


def test_problems_say_that_a_second_person_is_needed_for_offers(tmp_path):
    s = real_settings(tmp_path, approver_email=None, approver_password_hash=None, members_json="")
    assert any("second person" in p for p in s.problems())
    assert not any("second person" in p for p in real_settings(tmp_path).problems())


def test_the_worker_reads_the_same_settings_file_as_the_api_and_refuses_the_same_things(tmp_path, monkeypatch):
    env = tmp_path / "prod.env"
    env.write_text("DATABASE_URL=sqlite:///from-the-file.db\nDEMO_MODE=false\nSESSION_SECRET=change-me-to-a-long-random-string\n")
    monkeypatch.setenv("ENV_FILE", str(env))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.delenv("DEMO_MODE", raising=False)
    s = worker.load_settings()
    assert s.database_url == "sqlite:///from-the-file.db" and s.demo_mode is False
    with pytest.raises(ConfigError, match="SESSION_SECRET"):
        worker.main()  # the worker stops at start on an example secret, as the API does
    assert REAL_SECRET
