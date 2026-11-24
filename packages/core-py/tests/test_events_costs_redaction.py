from sendora_core.costs import CostTracker
from sendora_core.events import event_count, metric_total, recent_events, record_event, record_metric
from sendora_core.ratelimit import RateLimitExceeded, TokenBucket
from sendora_core.redaction import redact_obj, redact_text
import pytest


def test_events_redact_and_query(session):
    e = record_event(session, "lead.created", "lead", 7, {"email": "ada@example.test", "api_key": "abc", "note": "call +1 415 555 0100"})
    assert e.payload["email"] == "[email]" or "[email]" in e.payload["email"]
    assert e.payload["api_key"] == "[secret]"
    assert "[phone]" in e.payload["note"]
    record_event(session, "lead.scored")
    assert event_count(session, "lead.created") == 1
    assert [x.kind for x in recent_events(session, kind_prefix="lead.")] == ["lead.created", "lead.scored"]
    assert recent_events(session, after_id=e.id)[0].kind == "lead.scored"


def test_metrics(session):
    record_metric(session, "send", 2)
    record_metric(session, "send", 3, {"mailbox": "a"})
    assert metric_total(session, "send") == 5
    assert metric_total(session, "other") == 0


def test_costs(session):
    t = CostTracker(session)
    entry = t.record("claude-sonnet-5-5", "score", 1_000_000, 100_000)
    assert entry.usd == pytest.approx(3.0)
    t.record("unknown-model", "score", 10, 10)
    t.record("claude-haiku-5-5", "classify", 1000, 1000)
    assert t.total_usd() > 3.0
    assert set(t.by_purpose()) == {"score", "classify"}


def test_redaction_variants():
    assert "[secret]" in redact_text("key sk-abcdefghijklmnop here")
    assert "Bearer [secret]" in redact_text("Authorization: Bearer abcdefghijklmnop12345")
    assert "[id-number]" in redact_text("ssn 123-45-6789")
    assert redact_obj({"a": [{"password": "x"}, ("b@c.test",)]}) == {"a": [{"password": "[secret]"}, ("[email]",)]}
    assert redact_obj(5) == 5


def test_token_bucket():
    now = [0.0]
    b = TokenBucket(2, 1.0, clock=lambda: now[0])
    b.check("k")
    b.check("k")
    with pytest.raises(RateLimitExceeded) as ei:
        b.check("k")
    assert ei.value.retry_after > 0
    now[0] += 1.1
    b.check("k")
    b.check("other")
