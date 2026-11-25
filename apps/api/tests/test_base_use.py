"""How Slatehire uses the shared base 1.2.0: the viewer role, approvals with two people, the sign in burst and the model switch."""

import json

import pytest
from fastapi.testclient import TestClient

from conftest import login, make_ctx
from slatehire import scoring
from slatehire.api.app import create_app
from slatehire.offline_llm import OfflineBackend
from sendora_core.auth import WRITE_ROLES, read_session_token
from sendora_core.llm import LLMError

OPEN = {"/api/auth/login", "/api/auth/logout", "/api/webhooks/application"}
READ_ONLY_POSTS = {"/api/rubrics/{rubric_id}/check"}  # a POST that only reads: it lists what would stop a lock


def _login(client, who):
    return client.post("/api/auth/login", json={"email": who, "password": "demo-password-1"}).json()["token"]


def test_roles_come_from_the_base_and_the_viewer_cannot_write(client):
    roles = {w: read_session_token("test-secret-test-secret", _login(client, w))["role"] for w in ("owner@example.test", "approver@example.test", "viewer@example.test")}
    assert roles == {"owner@example.test": "owner", "approver@example.test": "approver", "viewer@example.test": "viewer"}
    assert "viewer" not in WRITE_ROLES


def test_a_viewer_can_read_everything_and_change_nothing(client):
    h = login(client, "viewer@example.test")
    for path in ("/api/overview", "/api/applications", "/api/pipeline", "/api/interviews", "/api/approvals", "/api/fairness"):
        assert client.get(path, headers=h).status_code == 200, path
    for path in ("/api/offers", "/api/audit", "/api/audit/verify"):  # pay terms and the audit log are for the owner and the approver (round 2 audit); the viewer once read offers
        assert client.get(path, headers=h).status_code == 403, path
    spec = client.get("/openapi.json").json()
    refused = 0
    for path, ops in spec["paths"].items():
        if not path.startswith("/api/") or path in OPEN | READ_ONLY_POSTS:
            continue
        for method in ops:
            if method.upper() == "GET":
                continue
            url = path.replace("{app_id}", "1").replace("{role_id}", "1").replace("{rubric_id}", "1").replace("{interview_id}", "1").replace("{offer_id}", "1").replace("{approval_id}", "1").replace("{task_id}", "1").replace("{category}", "ats")
            r = client.request(method.upper(), url, headers=h, json={})
            assert r.status_code == 403, (method, path, r.status_code)
            refused += 1
    assert refused > 25


def test_a_viewer_cannot_show_a_hidden_identity_but_the_owner_still_can(client):
    v, o = login(client, "viewer@example.test"), login(client, "owner@example.test")
    row = client.get("/api/applications", headers=o, params={"stage": "applied"}).json()[0]
    assert client.get(f"/api/applications/{row['id']}", headers=v, params={"reveal": "true"}).status_code == 403
    assert client.get(f"/api/applications/{row['id']}", headers=v).status_code == 200


def test_an_offer_is_decided_by_someone_other_than_the_person_who_asked(client):
    o, a = login(client, "owner@example.test"), login(client, "approver@example.test")
    pending = next(x for x in client.get("/api/approvals", headers=o).json() if x["status"] == "pending")
    own = client.post(f"/api/approvals/{pending['id']}/decide", headers=o, json={"approve": True})
    assert own.status_code == 409 and "someone else must decide" in own.text
    assert client.post(f"/api/approvals/{pending['id']}/decide", headers=a, json={"approve": False}).json() == {"status": "rejected"}


def test_the_seeded_demo_approval_has_a_different_requester_and_decider(ro):
    from sqlalchemy import select

    from sendora_core.models import Approval

    with ro.factory() as s:
        done = [x for x in s.scalars(select(Approval)) if x.status == "approved"]
    assert done and all(x.requested_by != x.decided_by for x in done)


def test_login_burst_comes_from_settings(tmp_path):
    ctx = make_ctx(tmp_path, login_burst=2)
    with TestClient(create_app(ctx.settings, ctx)) as c:
        codes = [c.post("/api/auth/login", json={"email": "owner@example.test", "password": "x"}).status_code for _ in range(4)]
    assert codes[:2] == [401, 401] and codes[2:] == [429, 429]


def test_llm_switch_defaults_to_the_offline_stand_in_and_answers_in_the_model_schema(ctx):
    crit = {"id": 3, "name": "Scheduling", "look_for": ["schedule", "rota"], "weight": 3}
    resume = "Built the weekly rota for 40 drivers and ran it for two years.\nEnjoys long walks."
    with ctx.factory() as s:
        llm = ctx.llm(s)
        assert isinstance(llm.backend, OfflineBackend) and llm.backend.is_live is False
        raw = llm.ask(f"[task:score_criterion]\nCRITERION_JSON: {json.dumps(crit)}", purpose="score", untrusted={"resume": resume})
        assert ctx.scorer(s) is None  # the default scores with the rules, no model object at all
    got = json.loads(raw)
    assert set(got) == {"shown", "level", "evidence", "reason"} and got["shown"] is True and 1 <= got["level"] <= 5 and got["evidence"] in resume


def test_llm_backend_anthropic_without_a_key_fails_loudly(tmp_path):
    ctx = make_ctx(tmp_path, llm_backend="anthropic", anthropic_api_key=None)  # explicit None: the shell may hold a real key
    with ctx.factory() as s, pytest.raises(LLMError):
        ctx.llm(s)
