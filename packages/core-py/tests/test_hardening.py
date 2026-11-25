"""Safety checks added after the strict security review: unsafe settings refuse to start, memory is bounded, decisions are atomic."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from sendora_core import approvals, jobs
from sendora_core.app import SESSION_COOKIE, create_base_app
from sendora_core.auth import make_session_token, read_session_token, verify_webhook_signature
from sendora_core.db import utcnow
from sendora_core.llm_anthropic import AnthropicBackend
from sendora_core.llm_types import LLMError
from sendora_core.models import Approval, Job
from sendora_core.ratelimit import RateLimitExceeded, TokenBucket
from sendora_core.settings import BaseAppSettings, ConfigError

GOOD_SECRET = "k3Jx9-Qw7Lm2Zp8Vt4Rn6Ys1Bd5Hf0Gc3Ua9Xe7Wi2"


def cfg(tmp_path, **kw):
    return BaseAppSettings(database_url=kw.pop("database_url", f"sqlite:///{tmp_path}/t.sqlite3"), _env_file=None, **kw)


# ---- session secret and demo settings (review H1, H2, H3, H6)
@pytest.mark.parametrize("secret", ["change-me-to-a-long-random-string", "dev-only-change-me-please-32-bytes!", "short-but-random-1234", "please-replace-this-value-with-random-text-now"])
def test_a_real_deployment_refuses_an_example_or_short_session_secret(tmp_path, secret):
    s = cfg(tmp_path, demo_mode=False, session_secret=secret)
    assert any("SESSION_SECRET" in e for e in s.runtime_errors())
    with pytest.raises(ConfigError):
        create_base_app(s)


def test_a_real_deployment_with_a_random_secret_starts(tmp_path):
    create_base_app(cfg(tmp_path, demo_mode=False, session_secret=GOOD_SECRET))


def test_a_demo_on_sqlite_starts_with_the_example_secret_but_not_on_a_server_database(tmp_path):
    create_base_app(cfg(tmp_path, demo_mode=True))
    s = cfg(tmp_path, demo_mode=True, database_url="postgresql+psycopg://u:p@db/x")
    assert any("DEMO_MODE" in e for e in s.runtime_errors())
    with pytest.raises(ConfigError):
        create_base_app(s)
    assert cfg(tmp_path, demo_mode=True, database_url="postgresql+psycopg://u:p@db/x", allow_demo_server=True).runtime_errors() == []


def test_the_error_message_never_holds_the_secret(tmp_path):
    with pytest.raises(ConfigError) as e:
        create_base_app(cfg(tmp_path, demo_mode=False, session_secret="change-me-to-a-long-random-string"))
    assert "change-me-to-a-long-random-string" not in str(e.value)


def test_demo_shortcuts_are_off_as_soon_as_an_owner_password_exists(tmp_path):
    class WithOwner(BaseAppSettings):
        owner_password_hash: str | None = None

    assert WithOwner(demo_mode=True, _env_file=None).demo_shortcuts is True
    assert WithOwner(demo_mode=True, owner_password_hash="$argon2id$x", _env_file=None).demo_shortcuts is False
    assert WithOwner(demo_mode=False, _env_file=None).demo_shortcuts is False


def test_docs_and_the_route_list_exist_only_in_a_demo(tmp_path):
    demo = TestClient(create_base_app(cfg(tmp_path, demo_mode=True)))
    real = TestClient(create_base_app(cfg(tmp_path, demo_mode=False, session_secret=GOOD_SECRET)))
    assert demo.get("/openapi.json").status_code == 200
    assert real.get("/openapi.json").status_code == 404 and real.get("/docs").status_code == 404


# ---- request size (review M3)
def test_a_body_over_the_limit_is_refused_before_the_app_reads_it(tmp_path):
    app = create_base_app(cfg(tmp_path, max_body_bytes=2048))
    read = []

    @app.post("/echo")
    async def echo(request):  # pragma: no cover - never reached for the large body
        read.append(1)
        return {}

    c = TestClient(app)
    assert c.post("/echo", content=b"x" * 5000).status_code == 413
    assert c.post("/echo", content=b"x" * 5000).json()["error"]["code"] == "http_413"
    assert read == []


def test_a_streamed_body_without_a_declared_length_is_counted(tmp_path):
    app = create_base_app(cfg(tmp_path, max_body_bytes=2048))

    @app.post("/echo")
    async def echo(request: __import__("fastapi").Request):
        return {"n": len(await request.body())}

    def chunks():
        for _ in range(10):
            yield b"y" * 500

    c = TestClient(app)
    assert c.post("/echo", content=chunks()).status_code == 413
    assert c.post("/echo", content=b"ok").json() == {"n": 2}


# ---- rate limiter memory (review M3)
def test_the_limiter_never_holds_more_than_max_keys():
    t = [0.0]
    b = TokenBucket(capacity=5, refill_per_sec=1.0, clock=lambda: t[0], max_keys=100)
    for i in range(5000):
        t[0] += 0.001
        b.check(f"k{i}")
    assert len(b._tokens) <= 100


def test_a_long_key_is_cut_and_a_limited_key_stays_limited():
    t = [0.0]
    b = TokenBucket(capacity=2, refill_per_sec=0.0001, clock=lambda: t[0], max_keys=10)
    b.check("a" * 1000)
    b.check("a" * 1000)
    with pytest.raises(RateLimitExceeded):
        b.check("a" * 1000)
    for i in range(50):
        b.check(f"other{i}")
    assert all(len(k) <= 256 for k in b._tokens)


# ---- tokens (review L3)
def test_a_non_ascii_signature_or_token_is_a_refusal_not_a_crash():
    assert read_session_token("s" * 40, "abc.é") is None
    assert read_session_token("s" * 40, "é.é") is None
    assert verify_webhook_signature("s" * 40, b"{}", "é") is False
    assert verify_webhook_signature("s" * 40, b"{}", "") is False


def test_a_forged_token_with_the_old_example_secret_is_refused_by_a_real_deployment(tmp_path):
    app = create_base_app(cfg(tmp_path, demo_mode=False, session_secret=GOOD_SECRET))

    @app.get("/who")
    def who(user=__import__("fastapi").Depends(__import__("sendora_core.app", fromlist=["require_role"]).require_role("owner"))):
        return user

    c = TestClient(app)
    forged = make_session_token("change-me-to-a-long-random-string", "x", "owner")
    assert c.get("/who", cookies={SESSION_COOKIE: forged}).status_code == 401
    assert c.get("/who", cookies={SESSION_COOKIE: make_session_token(GOOD_SECRET, "x", "owner")}).status_code == 200


# ---- approvals decided once (review M5)
def test_a_second_decision_on_the_same_approval_is_refused(session):
    a = approvals.request_approval(session, "send", "Send it", requested_by="system")
    approvals.decide(session, a.id, True, "ana", "owner")
    with pytest.raises(approvals.ApprovalError):
        approvals.decide(session, a.id, False, "bo", "approver")
    assert session.get(Approval, a.id).status == "approved"


def test_the_conditional_update_loses_when_another_writer_decided_in_between(session, monkeypatch):
    a = approvals.request_approval(session, "send", "Send it", requested_by="system")
    real_get = session.get

    def get_then_other_writer_wins(model, ident, *args, **kw):
        obj = real_get(model, ident, *args, **kw)
        session.execute(__import__("sqlalchemy").update(Approval).where(Approval.id == ident).values(status="approved", decided_by="other").execution_options(synchronize_session=False))
        return obj

    monkeypatch.setattr(session, "get", get_then_other_writer_wins)
    with pytest.raises(approvals.ApprovalError):
        approvals.decide(session, a.id, True, "ana", "owner")
    monkeypatch.undo()
    assert session.get(Approval, a.id).decided_by == "other"


# ---- jobs of a dead worker (review M8)
def test_a_job_whose_worker_died_goes_back_to_the_queue_and_then_fails_after_its_attempts(session):
    from datetime import timedelta

    job = jobs.enqueue(session, "reply_poll", max_attempts=2)
    claimed = jobs.claim_next(session)
    assert claimed.id == job.id and claimed.status == "running"
    assert jobs.claim_next(session) is None  # still running, inside the lease
    session.execute(__import__("sqlalchemy").update(Job).where(Job.id == job.id).values(run_at=utcnow() - timedelta(hours=2)).execution_options(synchronize_session=False))
    again = jobs.claim_next(session)
    assert again.id == job.id and again.attempts == 2
    session.execute(__import__("sqlalchemy").update(Job).where(Job.id == job.id).values(run_at=utcnow() - timedelta(hours=2)).execution_options(synchronize_session=False))
    assert jobs.claim_next(session) is None
    j = session.get(Job, job.id)
    session.refresh(j)
    assert j.status == "failed" and "worker stopped" in j.last_error


# ---- model address (review L8)
def test_the_model_key_is_never_sent_over_plain_http_to_another_host():
    with pytest.raises(LLMError):
        AnthropicBackend("sk-test", base_url="http://proxy.example.com")
    AnthropicBackend("sk-test", base_url="http://127.0.0.1:9999")
    AnthropicBackend("sk-test", base_url="https://api.anthropic.com")


# ---- login helpers (review M1, L2)
def test_clean_email_gives_one_spelling_and_a_bounded_length():
    from sendora_core.auth import clean_email

    assert clean_email("  Owner@Example.COM \t") == clean_email("owner@example.com") == "owner@example.com"
    assert len(clean_email("a" * 5000)) == 254
    assert clean_email(None) == ""


def test_a_missing_account_takes_the_same_path_and_never_passes():
    from sendora_core.auth import hash_password, verify_password_or_dummy

    h = hash_password("a-good-password-1")
    assert verify_password_or_dummy("a-good-password-1", h) is True
    assert verify_password_or_dummy("wrong-password-1", h) is False
    assert verify_password_or_dummy("a-good-password-1", None) is False
