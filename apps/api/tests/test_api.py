import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from conftest import HOOK, login, make_settings
from slatehire.api.app import create_app

MOVE = {"to": "declined", "note": "The role needs written examples and none were shown."}


def H(c, who="owner@example.test"):
    return login(c, who)


def apps(c, h, **q):
    return c.get("/api/applications", headers=h, params=q).json()


def test_every_route_needs_a_session_except_login_logout_and_the_signed_webhook(client):
    spec = client.get("/openapi.json").json()
    open_paths = {"/api/auth/login", "/api/auth/logout", "/api/webhooks/application"}
    n = 0
    for path, ops in spec["paths"].items():
        if not path.startswith("/api/") or path in open_paths:
            continue
        for method in ops:
            url = path.replace("{app_id}", "1").replace("{role_id}", "1").replace("{rubric_id}", "1").replace("{interview_id}", "1").replace("{offer_id}", "1").replace("{approval_id}", "1").replace("{task_id}", "1").replace("{category}", "ats")
            r = client.request(method.upper(), url, json={})
            assert r.status_code == 401, (method, path, r.status_code)
            n += 1
    assert n > 40
    assert client.get("/health").status_code == 200


def test_login_rate_limit_and_wrong_password(client):
    assert client.post("/api/auth/login", json={"email": "owner@example.test", "password": "wrong"}).status_code == 401
    assert 429 in {client.post("/api/auth/login", json={"email": "x@example.test", "password": "bad"}).status_code for _ in range(8)}


def test_overview_is_seeded_and_evidence_is_exactly_valid(client):
    h = H(client)
    o = client.get("/api/overview", headers=h).json()
    assert sum(o["funnel"].values()) == 90 and o["roles"] == 3 and o["roles_unlocked"] == 0 and o["pending_approvals"] == 1
    assert o["evidence"]["invalid"] == 0 and o["evidence"]["valid_percent"] == 100.0 and o["evidence"]["quotes"] > 100
    assert client.get("/api/evals", headers=h).json()["quote_check"]["invalid"] == 0


def test_blind_mode_hides_identity_in_the_list_the_board_and_the_workspace(client):
    h = H(client)
    rows = apps(client, h, stage="applied")
    assert rows and all(r["hidden"] and r["name"] == f"Candidate {r['code']}" for r in rows)
    cand = rows[0]
    w = client.get(f"/api/applications/{cand['id']}", headers=h, params={"reveal": "true"}).json()
    assert w["blind"]["enforced"] and w["person"]["hidden"] and w["person"]["email"] is None
    blob = json.dumps(w)
    assert '"original"' not in blob
    board = client.get("/api/pipeline", headers=h).json()
    assert all(c["hidden"] for c in board["applied"]["cards"]) and not any(c["hidden"] for c in board["shortlisted"]["cards"])


def test_after_the_shortlist_identity_is_shown_and_a_reveal_is_audited(client):
    h = H(client)
    sl = apps(client, h, stage="shortlisted")[0]
    w0 = client.get(f"/api/applications/{sl['id']}", headers=h).json()
    assert w0["person"]["hidden"] and not w0["blind"]["enforced"]  # not enforced, but the default view is still the hidden one
    w = client.get(f"/api/applications/{sl['id']}", headers=h, params={"reveal": "true"}).json()
    assert not w["person"]["hidden"] and w["person"]["email"] and any(p.get("original") for p in w["resume"]["pieces"] if p["kind"] == "identity")
    log = client.get("/api/audit", headers=h).json()
    assert any(e["action"] == "identity.revealed" and e["target"] == f"application:{sl['id']}" for e in log)


def test_evidence_highlights_line_up_with_the_resume_text(client):
    h = H(client)
    a = apps(client, h, stage="shortlisted")[0]
    w = client.get(f"/api/applications/{a['id']}", headers=h).json()
    shown = "".join(p["text"] for p in w["resume"]["pieces"])
    marked = [p for p in w["resume"]["pieces"] if p["kind"] == "text" and p["criteria"]]
    assert marked
    quotes = [q["text"] for it in w["score"]["items"] for q in it["quotes"]]
    assert quotes and all(q in shown for q in quotes)


def test_a_person_moves_people_and_the_reason_is_required(client):
    h = H(client)
    a = apps(client, h, stage="applied")[0]
    r = client.post(f"/api/applications/{a['id']}/move", headers=h, json={"to": "declined", "note": "no"})
    assert r.status_code == 400 and "reason" in r.json()["error"]["message"]
    ok = client.post(f"/api/applications/{a['id']}/move", headers=h, json=MOVE)
    assert ok.status_code == 200 and ok.json()["stage"] == "declined"
    assert client.post(f"/api/applications/{a['id']}/move", headers=h, json={"to": "shortlisted"}).status_code == 400


def test_an_offer_needs_a_second_person_and_nothing_is_sent_to_the_candidate(client):
    h, h2 = H(client), H(client, "approver@example.test")
    ap = next(a for a in client.get("/api/approvals", headers=h).json() if a["status"] == "pending")
    r = client.post(f"/api/approvals/{ap['id']}/decide", headers=h, json={"approve": True})
    assert r.status_code == 409 and "someone else must decide" in r.json()["error"]["message"]
    off_id = ap["payload"]["offer_id"]
    assert client.post(f"/api/offers/{off_id}/hand-off", headers=h).status_code == 400  # not approved yet
    assert client.post(f"/api/approvals/{ap['id']}/decide", headers=h2, json={"approve": True}).status_code == 200
    out = client.post(f"/api/offers/{off_id}/hand-off", headers=h)
    assert out.status_code == 200 and "Open it in your signing tool" in out.json()["detail"]
    offers = {o["id"]: o for o in client.get("/api/offers", headers=h).json()}
    assert offers[off_id]["status"] == "handed_off"


def test_scorecard_flow_through_the_api_hides_others_until_you_send_yours(client):
    h, h2 = H(client), H(client, "approver@example.test")
    shortlisted = apps(client, h, stage="shortlisted")
    iv = client.post(f"/api/applications/{shortlisted[0]['id']}/interviews", headers=h, json={"interviewers": ["owner@example.test", "approver@example.test"], "starts_at": "2026-12-08T10:00:00Z", "minutes": 45})
    assert iv.status_code == 200
    one = client.get(f"/api/interviews/{iv.json()['id']}", headers=h2).json()
    assert one["hidden"] and one["can_submit"] and len(one["kit"]) == 5
    ratings = {k["criterion_id"]: 4 for k in one["kit"]}
    assert client.post(f"/api/interviews/{one['id']}/scorecards", headers=h2, json={"ratings": ratings, "comments": {}, "recommendation": "yes"}).status_code == 200
    again = client.post(f"/api/interviews/{one['id']}/scorecards", headers=h2, json={"ratings": ratings, "comments": {}, "recommendation": "yes"})
    assert again.status_code == 400
    mine = client.get(f"/api/interviews/{one['id']}", headers=h2).json()
    assert not mine["hidden"] and mine["summary"]["submitted"] == 1
    assert client.get(f"/api/interviews/{one['id']}", headers=h).json()["hidden"]  # the owner has not sent theirs


def test_the_demo_invite_stays_inside_the_app(client):
    h = H(client)
    a = apps(client, h, stage="shortlisted")[0]
    iv = client.post(f"/api/applications/{a['id']}/interviews", headers=h, json={"interviewers": ["owner@example.test"], "starts_at": "2026-12-08T10:00:00Z"}).json()["id"]
    out = client.post(f"/api/interviews/{iv}/invite", headers=h, json={"confirm": True}).json()
    assert out["sent"] is True and "Nothing is sent" in out["reason"]
    assert client.post(f"/api/interviews/{iv}/invite", headers=h, json={}).json()["sent"] is True  # the offline adapter has nothing to confirm
    assert client.get(f"/api/interviews/{iv}", headers=h).json()["status"] == "invited"


def test_intake_paste_csv_file_and_url_guard(client):
    h = H(client)
    text = "Customer Support Specialist, Acme Co, 2020 to 2026\n* Wrote replies to customer emails every day and trained 3 colleagues.\n* Ran the helpdesk ticket queue.\n"
    r = client.post("/api/applicants", headers=h, json={"name": "Odalys Thorne", "email": "odalys@mail.example.test", "role": "support", "resume_text": text})
    assert r.json()["status"] == "added"
    assert client.post("/api/applicants", headers=h, json={"name": "Odalys Thorne", "email": "odalys@mail.example.test", "role": "support", "resume_text": text}).json()["status"] == "duplicate"
    assert client.post("/api/applicants", headers=h, json={"name": "Nobody Here", "role": "support", "resume_text": "short"}).json()["status"] == "rejected"
    assert client.post("/api/applicants", headers=h, json={"name": "Nobody Here", "role": "nope", "resume_text": text}).status_code == 400
    csv = "name,email,role,resume_text\nIvo Barrow,ivo@mail.example.test,ops,\"" + text.replace("Support", "Operations") + "\"\nBad Row,,ghost,\"" + text + "\"\n"
    out = client.post("/api/applicants/csv", headers=h, content=csv.encode()).json()
    assert out["added"] == 1 and out["rejected"] == 1 and "ghost" in out["problems"][0]
    f = client.post("/api/applicants/file?role=support&name=Pell Raine", headers={**h, "x-filename": "cv.txt"}, content=text.encode())
    assert f.json()["status"] == "added"
    blocked = client.post("/api/applicants", headers=h, json={"name": "Url Person", "role": "support", "resume_url": "http://169.254.169.254/latest/meta-data"})
    assert blocked.status_code == 400
    assert client.post("/api/applicants/csv", headers=h, content=b"\xff\xfe").status_code == 400


def test_a_new_applicant_is_scored_by_the_job_and_stays_applied(client):
    h = H(client)
    client.post("/api/demo/tick", headers=h)
    o = client.get("/api/overview", headers=h).json()
    assert sum(o["funnel"].values()) == 91 and o["unscored"] == 0
    new = max(apps(client, h), key=lambda r: r["id"])
    assert new["stage"] == "applied" and new["total"] is not None


def test_signed_webhook_adds_an_applicant_and_a_bad_signature_is_refused(client):
    body = json.dumps({"name": "Hooked Person", "email": "hp@mail.example.test", "role": "analyst", "resume_text": "Data Analyst, Fictional Co\n* Wrote SQL queries and joins on the warehouse database every week.\n* Built dashboards.\n"}).encode()
    good = hmac.new(HOOK.encode(), body, hashlib.sha256).hexdigest()
    assert client.post("/api/webhooks/application", content=body, headers={"x-signature": "0" * 64}).status_code == 401
    assert client.post("/api/webhooks/application", content=body).status_code == 401
    ok = client.post("/api/webhooks/application", content=body, headers={"x-signature": good})
    assert ok.status_code == 200 and ok.json()["status"] == "added"
    assert client.post("/api/webhooks/application", content=b"{}", headers={"x-signature": hmac.new(HOOK.encode(), b"{}", hashlib.sha256).hexdigest()}).status_code == 400


def test_rubric_lifecycle_through_the_api(client):
    h = H(client)
    role = client.post("/api/roles", headers=h, json={"title": "Warehouse Lead", "description": "Runs the floor."}).json()
    crit = [{"id": "x1", "name": "Safety", "weight": 3, "anchors": {"1": "Has seen it done.", "3": "Has done it alone.", "5": "Has led it and taught it."}, "look_for": ["safety"], "question": ""}]
    r = client.post(f"/api/roles/{role['id']}/rubric", headers=h, json={"criteria": crit})
    rid = r.json()["id"]
    chk = client.post(f"/api/rubrics/{rid}/check", headers=h).json()["problems"]
    assert chk and "between 2 and 10" in chk[0]
    assert client.post(f"/api/rubrics/{rid}/lock", headers=h).status_code == 400
    crit.append({**crit[0], "id": "x2", "name": "Forklift"})
    assert client.put(f"/api/rubrics/{rid}", headers=h, json={"criteria": crit}).status_code == 200
    locked = client.post(f"/api/rubrics/{rid}/lock", headers=h).json()
    assert locked["locked"] and locked["signature_ok"] and locked["fingerprint"]
    assert client.put(f"/api/rubrics/{rid}", headers=h, json={"criteria": crit[:1]}).status_code == 400
    v2 = client.post(f"/api/roles/{role['id']}/rubric", headers=h, json={"blind": False}).json()
    assert v2["version"] == 2 and not v2["locked"] and v2["blind"] is False


def test_only_the_owner_deletes_and_only_the_owner_imports_labels_and_a_delete_really_deletes(client):
    h, h2 = H(client), H(client, "approver@example.test")
    a = apps(client, h, stage="declined")[0]
    assert client.delete(f"/api/candidates/{a['id']}", headers=h2).status_code == 403
    assert client.delete(f"/api/candidates/{a['id']}", headers=h).status_code == 200
    w = client.get(f"/api/applications/{a['id']}", headers=h, params={"reveal": "true"}).json()
    assert w["deleted"] and w["person"]["name"] == "(deleted)" and w["resume"]["pieces"] == []
    assert client.post("/api/fairness/labels", headers=h2, json={"labels": {"A001": "Q"}}).status_code == 403


def test_fairness_report_endpoint_and_kill_switch(client):
    h = H(client)
    assert client.get("/api/fairness", headers=h).json()["report"] is None
    assert client.post("/api/fairness/run", headers=h, json={"role": "all", "min_group": 10}).status_code == 200
    rep = client.get("/api/fairness", headers=h).json()["report"]["payload"]
    assert rep["disclaimer"].startswith("This is an indicator") and set(rep["stages"]) == {"shortlisted", "interviewed", "offered", "hired"}
    assert client.post("/api/fairness/run", headers=h, json={"role": "all", "min_group": 1}).status_code == 422
    s = client.post("/api/settings", headers=h, json={"kill_switch": True}).json()
    assert s["kill_switch"] and client.post("/api/settings", headers=H(client, "approver@example.test"), json={"kill_switch": False}).status_code == 403


def test_onboarding_tasks_can_be_ticked_and_added(client):
    h = H(client)
    ob = client.get("/api/onboarding", headers=h).json()
    assert len(ob) == 1 and ob[0]["progress"]["30"]["total"] >= 5
    t = ob[0]["tasks"][0]
    assert client.patch(f"/api/onboarding/tasks/{t['id']}", headers=h, json={"done": True}).json()["done"]
    bad = client.post(f"/api/applications/{ob[0]['application_id']}/onboarding/tasks", headers=h, json={"phase": 45, "title": "x" * 10, "due_on": "2027-01-01"})
    assert bad.status_code == 400
    assert client.post(f"/api/applications/{ob[0]['application_id']}/onboarding/tasks", headers=h, json={"phase": 30, "title": "Lunch with the team", "due_on": "2027-01-20"}).status_code == 200


def test_demo_routes_do_not_exist_outside_demo_mode(tmp_path):
    c = TestClient(create_app(make_settings(tmp_path, demo_mode=False, owner_password_hash="x")))
    assert c.post("/api/auth/login", json={"email": "owner@example.test", "password": "demo-password-1"}).status_code == 401
