import pytest
from pydantic import BaseModel

from sendora_core.adapters import AdapterError, AdapterRegistry, AdapterSpec
from sendora_core.costs import CostTracker
from sendora_core.evals import EvalCase, run_eval
from sendora_core.llm import LLM, FixtureLLM, LLMError, LLMResponse, build_llm, fixture_key


class Verdict(BaseModel):
    intent: str
    confidence: float


def make(settings, session, backend):
    return LLM(settings, backend, CostTracker(session), retries=2, sleep=lambda _: None)


def test_structured_ok_and_cost(settings, session):
    llm = make(settings, session, FixtureLLM(default='Sure: {"intent": "interested", "confidence": 0.9}'))
    v = llm.structured("classify", Verdict, purpose="classify", kind="bulk")
    assert v.intent == "interested"
    assert CostTracker(session).total_usd() > 0


def test_structured_repairs_once_then_fails(settings, session):
    replies = iter(["not json", '{"intent": "x", "confidence": 1}'])

    class B:
        def complete(self, **kw):
            return LLMResponse(next(replies), 10, 10, kw["model"])

    assert make(settings, session, B()).structured("p", Verdict, purpose="t").intent == "x"
    with pytest.raises(LLMError):
        make(settings, session, FixtureLLM(default="never json")).structured("p", Verdict, purpose="t")


def test_retries_then_raise(settings, session):
    calls = []

    class Flaky:
        def complete(self, **kw):
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionError("boom")
            return LLMResponse("ok", 1, 1, kw["model"])

    assert make(settings, session, Flaky()).ask("x", purpose="t") == "ok"

    class Dead:
        def complete(self, **kw):
            raise ConnectionError("down")

    with pytest.raises(LLMError, match="3 tries"):
        make(settings, session, Dead()).ask("x", purpose="t")


def test_fixture_lookup_and_missing(settings, session, tmp_path):
    backend = FixtureLLM()
    llm = make(settings, session, backend)
    with pytest.raises(LLMError, match="No recorded fixture"):
        llm.ask("hi", purpose="t")
    k = backend.calls[0]
    (tmp_path / f"{k}.json").write_text('{"text": "recorded"}')
    llm2 = make(settings, session, FixtureLLM(directory=tmp_path))
    assert llm2.ask("hi", purpose="t") == "recorded"
    assert len(fixture_key('m', 's', 'p')) == 16


def test_build_llm_demo(settings, session):
    llm = build_llm(settings, CostTracker(session), default="ok")
    assert llm.ask("x", purpose="t") == "ok"


def test_adapter_registry():
    from sendora_core.settings import BaseAppSettings

    reg = AdapterRegistry(BaseAppSettings(_env_file=None))
    reg.register(AdapterSpec("email", "seed", "A", lambda s: "seed-email"))
    reg.register(AdapterSpec("email", "sendkit", "B", lambda s: "sendkit", notes="UNVERIFIED live"))
    assert reg.get("email", "seed") == "seed-email"
    with pytest.raises(AdapterError, match="Known for email: seed, sendkit"):
        reg.get("email", "nope")
    with pytest.raises(AdapterError):
        reg.register(AdapterSpec("email", "seed", "A", lambda s: 1))
    with pytest.raises(AdapterError):
        reg.register(AdapterSpec("x", "y", "Z", lambda s: 1))
    assert reg.by_tier() == {"A": 1, "B": 1, "C": 0}
    assert all(r["live_verified"] is False for r in reg.describe())


def test_eval_runner():
    cases = [EvalCase("a", 1, 2), EvalCase("b", 2, 4), EvalCase("c", 3, 99)]

    def predict(x):
        if x == 3:
            raise ValueError("bad")
        return x * 2

    r = run_eval("double", cases, predict)
    assert (r.total, r.passed) == (3, 2)
    assert r.failures[0]["id"] == "c" and "error" in r.failures[0]["got"]
    assert "2/3" in r.summary()
    assert run_eval("empty", [], predict).pass_rate == 0.0
