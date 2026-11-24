import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from sendora_core.app import create_base_app, get_db, require_role, SESSION_COOKIE
from sendora_core.auth import hash_password, make_session_token, read_session_token, verify_password, verify_webhook_signature
from sendora_core.events import record_event
from sendora_core.jobs import Worker, enqueue
from sendora_core.models import Job
from sendora_core.sse import event_stream, format_sse
from sendora_core.db import session_scope


def test_job_success_and_retry_and_fail(factory):
    seen = []

    def ok(s, p):
        seen.append(p)
        return {"n": 1}

    attempts = {"n": 0}

    def flaky(s, p):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("try again")

    def bad(s, p):
        raise RuntimeError("always")

    w = Worker(factory, {"ok": ok, "flaky": flaky, "bad": bad}, backoff_s=0)
    with session_scope(factory) as s:
        enqueue(s, "ok", {"a": 1})
        enqueue(s, "flaky")
        enqueue(s, "bad", max_attempts=2)
        enqueue(s, "unknown", max_attempts=1)
        enqueue(s, "later", delay_s=3600)
    assert w.drain() == 6
    with session_scope(factory) as s:
        by = {j.kind: j for j in s.query(Job)}
    assert by["ok"].status == "done" and by["ok"].result == {"n": 1}
    assert by["flaky"].status == "done" and by["flaky"].attempts == 2
    assert by["bad"].status == "failed" and by["bad"].attempts == 2 and "always" in by["bad"].last_error
    assert by["unknown"].status == "failed" and "No handler" in by["unknown"].last_error
    assert by["later"].status == "queued"
    assert seen == [{"a": 1}]
    assert w.run_once() is False


def test_auth():
    h = hash_password("correct horse")
    assert verify_password("correct horse", h) and not verify_password("wrong", h)
    assert not verify_password("x", "not-a-hash")
    with pytest.raises(ValueError):
        hash_password("short")
    t = make_session_token("s" * 20, "onit", "owner")
    assert read_session_token("s" * 20, t) == {"user": "onit", "role": "owner"}
    assert read_session_token("other-secret-xxxxx", t) is None
    assert read_session_token("s" * 20, t + "x") is None
    assert read_session_token("s" * 20, "garbage") is None
    expired = make_session_token("s" * 20, "o", "owner", ttl_s=10, now=time.time() - 100)
    assert read_session_token("s" * 20, expired) is None
    with pytest.raises(ValueError):
        make_session_token("s" * 20, "o", "guest")


def test_webhook_signature():
    import hashlib, hmac

    sig = hmac.new(b"k", b"body", hashlib.sha256).hexdigest()
    assert verify_webhook_signature("k", b"body", sig.upper())
    assert not verify_webhook_signature("k", b"body2", sig)


def test_sse_format_and_stream(factory):
    assert format_sse("x", {"a": 1}, 3) == 'id: 3\nevent: x\ndata: {"a": 1}\n\n'
    with session_scope(factory) as s:
        record_event(s, "lead.created", "lead", 1)

    async def collect():
        return [f async for f in event_stream(factory, poll_s=0, max_idle_polls=2)]

    frames = asyncio.run(collect())
    assert frames[0].startswith("id: 1\nevent: lead.created")
    assert frames[-1] == ": heartbeat\n\n"

    async def stopped():
        return [f async for f in event_stream(factory, is_disconnected=lambda: True)]

    assert asyncio.run(stopped()) == []


def test_base_app(settings, factory):
    app = create_base_app(settings, factory)

    @app.get("/secret")
    def secret(user=__import__("fastapi").Depends(require_role("owner"))):
        return user

    @app.get("/boom")
    def boom(db=__import__("fastapi").Depends(get_db)):
        from sendora_core.safety import guard_write

        guard_write(settings, "send")

    c = TestClient(app)
    r = c.get("/health")
    assert r.json()["status"] == "ok" and r.headers["x-request-id"]
    assert c.get("/ready").json() == {"status": "ready"}
    assert c.get("/secret").status_code == 401
    assert c.get("/secret").json()["error"]["code"] == "http_401"
    tok = make_session_token(settings.session_secret, "a", "approver")
    assert c.get("/secret", cookies={SESSION_COOKIE: tok}).status_code == 403
    tok = make_session_token(settings.session_secret, "onit", "owner")
    assert c.get("/secret", headers={"x-session": tok}).json() == {"user": "onit", "role": "owner"}
    r = c.get("/boom")
    assert r.status_code == 409 and r.json()["error"]["code"] == "DraftModeError"
    assert c.get("/health", headers={"x-request-id": "abc"}).headers["x-request-id"] == "abc"


def test_rate_limit_via_app(settings, factory):
    app = create_base_app(settings, factory)
    c = TestClient(app)
    codes = [c.get("/health").status_code for _ in range(130)]
    assert 429 in codes


def test_viewer_role_read_only(settings, factory):
    from fastapi import Depends

    from sendora_core.app import require_read, require_write
    from sendora_core.auth import READ_ROLES, WRITE_ROLES, can_read, can_write

    assert READ_ROLES == ("owner", "approver", "viewer") and WRITE_ROLES == ("owner", "approver")
    assert can_read("viewer") and not can_write("viewer") and can_write("approver") and not can_read("guest")
    t = make_session_token("s" * 20, "v", "viewer")
    assert read_session_token("s" * 20, t) == {"user": "v", "role": "viewer"}

    app = create_base_app(settings, factory)

    @app.get("/items")
    def items(user=Depends(require_read())):
        return {"who": user["user"]}

    @app.post("/items")
    def add_item(user=Depends(require_read())):  # a route author used the read guard on a write
        return {"added": True}

    @app.post("/items2")
    def add_item2(user=Depends(require_write())):
        return {"added": True}

    @app.get("/admin")
    def admin(user=Depends(require_role("owner"))):
        return user

    c = TestClient(app)
    tok = lambda role: {"x-session": make_session_token(settings.session_secret, role, role)}  # noqa: E731
    assert c.get("/items").status_code == 401
    for role in ("owner", "approver", "viewer"):
        assert c.get("/items", headers=tok(role)).json() == {"who": role}
    assert c.post("/items", headers=tok("owner")).json() == {"added": True}
    assert c.post("/items", headers=tok("approver")).status_code == 200
    r = c.post("/items", headers=tok("viewer"))
    assert r.status_code == 403 and "read only" in r.json()["error"]["message"]
    assert c.post("/items2", headers=tok("viewer")).status_code == 403
    assert c.post("/items2", headers=tok("approver")).status_code == 200
    assert c.get("/admin", headers=tok("viewer")).status_code == 403  # existing owner only routes stay closed to viewers
    assert c.get("/admin", headers=tok("owner")).status_code == 200
