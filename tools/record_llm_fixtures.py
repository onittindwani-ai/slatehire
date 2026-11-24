"""Record the model answers for the first seed applications into data/llm_fixtures/, so the demo can replay them with LLM_BACKEND=fixture SCORER=model and no account.

IMPORTANT: these are NOT answers of a real model. The recording goes through the real anthropic code path (request building, schema, response parsing, the checks by code)
against a local fake server that answers with the offline stand in. So the fixtures prove the replay path and the request shape, not model quality. Replace them with a
recording from a real key (LLM_RECORD=true, LLM_BACKEND=anthropic, SCORER=model) when you have one. Never commit recordings made from real applicants: the fixture holds the
redacted resume text the model read.

What is recorded: one call per criterion for the first 8 applications of the demo world (SCORER=model). Any other application falls back to the rules with a note.
Replay with LLM_BACKEND=fixture LLM_FIXTURES_DIR=data/llm_fixtures SCORER=model.

Run: python tools/record_llm_fixtures.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "apps" / "api" / "src"), str(ROOT)]

from mock.anthropic_mock import FakeAnthropic  # noqa: E402
from slatehire import demo, evidence, rubric_service, scoring  # noqa: E402
from slatehire.config import Settings  # noqa: E402
from slatehire.context import Ctx  # noqa: E402
from slatehire.models import Application, Resume  # noqa: E402
from slatehire.offline_llm import OfflineBackend  # noqa: E402
from sendora_core import models as _core  # noqa: E402,F401
from sendora_core.db import Base, make_engine, make_session_factory  # noqa: E402
from sendora_core.llm import reset_budgets  # noqa: E402
from sqlalchemy import select  # noqa: E402

OUT = ROOT / "data" / "llm_fixtures"
FIRST = 8


def stand_in(body: dict) -> str:
    return OfflineBackend().complete(model=body["model"], system=body.get("system", ""), prompt=body["messages"][0]["content"], max_tokens=body["max_tokens"]).text


def _settings(tmp: str, **kw) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp}/w.sqlite3", session_secret="record-secret-record-secret", seed_dir=str(ROOT / "data"), export_dir=f"{tmp}/exports",
                    _env_file=None, scorer="model", llm_max_retries=0, **{"anthropic_api_key": None, **kw})


def _world(tmp: str, **kw) -> Ctx:
    eng = make_engine(f"sqlite:///{tmp}/w.sqlite3")
    Base.metadata.create_all(eng)
    return Ctx(_settings(tmp, **kw), make_session_factory(eng))


def _score_first(ctx: Ctx) -> dict:
    """Score the first applications with the model scorer of `ctx`; return the numbers a test or a person needs."""
    reset_budgets()
    calls = fallbacks = invalid = 0
    with ctx.factory() as s:
        for app in list(s.scalars(select(Application).order_by(Application.id)))[:FIRST]:
            rub = rubric_service.latest(s, app.role_id, locked_only=True)
            res = s.scalars(select(Resume).where(Resume.application_id == app.id)).one()
            scorer = ctx.scorer(s)
            out = scoring.score_resume(rub.criteria, res.redacted_text, scorer)
            calls += scorer.calls
            fallbacks += scorer.fallbacks
            invalid += sum(1 for it in out["items"] for q in it["quotes"] if not evidence.verify_quote(q["text"], res.redacted_text).ok)
    return {"calls": calls, "fallbacks": fallbacks, "model_calls": calls - fallbacks, "quote_invalid": invalid}


def record(out: Path = OUT, work: Path | None = None) -> dict:
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    if work is not None:
        Path(work).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp, FakeAnthropic(stand_in) as fake:
        base = _world(tmp)
        with base.factory() as s:
            demo.reset(s, base)
        ctx = _world(tmp, llm_backend="anthropic", anthropic_api_key="fake-key-for-local-server", anthropic_base_url=fake.url, llm_record=True, llm_fixtures_dir=str(out))
        info = _score_first(ctx)
    files = len(list(out.glob("*.json")))
    (out / "README.txt").write_text(
        "Recorded from a LOCAL FAKE server that answers with the offline stand in. These are NOT answers of a real model.\n"
        "They prove the replay path and the request shape only. Replay with LLM_BACKEND=fixture LLM_FIXTURES_DIR=data/llm_fixtures SCORER=model.\n"
        "Recorded: one call per criterion for the first 8 applications of the demo world. Regenerate: python tools/record_llm_fixtures.py\n", encoding="utf-8")
    return {**info, "files": files, "requests_to_fake_server": len(fake.requests)}


def replay_scores(fixtures: Path, work: Path | None = None) -> dict:
    """Score the same applications from recorded fixtures only (no server). A missing fixture falls back to the rules."""
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        base = _world(tmp)
        with base.factory() as s:
            demo.reset(s, base)
        return _score_first(_world(tmp, llm_backend="fixture", llm_fixtures_dir=str(fixtures)))


if __name__ == "__main__":
    print(json.dumps(record()))
