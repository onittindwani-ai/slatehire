"""Found by walking every screen as a first time owner (Round 5). One test per defect that lives in the API."""

from pathlib import Path

from conftest import make_settings
from fastapi.testclient import TestClient
from slatehire.api.app import create_app
from test_api import H, apps

TEXT = "Customer Support Specialist, Acme Co, 2020 to 2026\n* Wrote replies to customer emails every day and trained 3 colleagues.\n* Ran the helpdesk ticket queue.\n"


def pending_offer(client, h):
    ap = next(a for a in client.get("/api/approvals", headers=h).json() if a["status"] == "pending")
    return ap, next(o for o in client.get("/api/offers", headers=h).json() if o["approval"] and o["approval"]["id"] == ap["id"])


def test_declining_someone_closes_their_waiting_offer_and_nobody_can_approve_it_later(client):
    h, h2 = H(client), H(client, "approver@example.test")
    ap, offer = pending_offer(client, h)
    r = client.post(f"/api/applications/{offer['application_id']}/move", headers=h, json={"to": "declined", "note": "Withdrew after the final round."})
    assert r.status_code == 200
    now = {o["id"]: o for o in client.get("/api/offers", headers=h).json()}[offer["id"]]
    assert now["status"] == "withdrawn" and now["approval"]["status"] == "rejected"
    late = client.post(f"/api/approvals/{ap['id']}/decide", headers=h2, json={"approve": True})
    assert late.status_code == 409
    assert client.post(f"/api/offers/{offer['id']}/hand-off", headers=h).status_code == 400
    assert client.post(f"/api/offers/{offer['id']}/request-approval", headers=h).status_code == 400


def test_an_approved_offer_for_someone_who_then_left_is_not_written_to_a_file(client):
    h, h2 = H(client), H(client, "approver@example.test")
    ap, offer = pending_offer(client, h)
    assert client.post(f"/api/approvals/{ap['id']}/decide", headers=h2, json={"approve": True}).status_code == 200
    client.post(f"/api/applications/{offer['application_id']}/move", headers=h, json={"to": "withdrawn", "note": "Took another job elsewhere."})
    out = client.post(f"/api/offers/{offer['id']}/hand-off", headers=h)
    assert out.status_code == 400 and "left the process" in out.json()["error"]["message"]


def test_deleting_personal_data_also_removes_the_name_from_the_offer_text_and_file(client, tmp_path):
    h = H(client)
    done = next(o for o in client.get("/api/offers", headers=h).json() if o["status"] == "handed_off")
    name = done["name"]
    assert name in done["body"]
    assert client.delete(f"/api/candidates/{done['application_id']}", headers=h).status_code == 200
    after = {o["id"]: o for o in client.get("/api/offers", headers=h).json()}[done["id"]]
    assert name not in after["body"] and name not in after["terms"] and "(deleted)" in after["body"]
    f = Path(make_settings(tmp_path).export_dir) / done["handoff_ref"]
    if f.exists():
        assert name not in f.read_text()


def test_marking_someone_hired_starts_their_onboarding_plan(client):
    h, h2 = H(client), H(client, "approver@example.test")
    ap, offer = pending_offer(client, h)
    assert client.post(f"/api/approvals/{ap['id']}/decide", headers=h2, json={"approve": True}).status_code == 200
    assert client.post(f"/api/offers/{offer['id']}/hand-off", headers=h).status_code == 200
    r = client.post(f"/api/applications/{offer['application_id']}/move", headers=h, json={"to": "hired", "note": "Signed offer received."})
    assert r.status_code == 200 and r.json()["onboarding_tasks"] >= 11
    plans = {p["application_id"]: p for p in client.get("/api/onboarding", headers=h).json()}
    assert offer["application_id"] in plans and plans[offer["application_id"]]["progress"]["30"]["total"] >= 4


def test_an_applicant_needs_a_real_name_and_a_valid_email(client):
    h = H(client)
    blank = client.post("/api/applicants", headers=h, json={"name": "   ", "role": "support", "resume_text": TEXT}).json()
    assert blank["status"] == "rejected" and "name" in blank["reason"]
    bad = client.post("/api/applicants", headers=h, json={"name": "Odalys Thorne", "email": "not-an-email", "role": "support", "resume_text": TEXT}).json()
    assert bad["status"] == "rejected" and "email" in bad["reason"]
    short = client.post("/api/applicants", headers=h, json={"name": "Odalys Thorne", "role": "support", "resume_text": "short"}).json()
    assert short["status"] == "rejected" and "too little text" in short["reason"]
    csv = "name,email,role,resume_text\nPell Raine,nope,support,\"" + TEXT + "\"\nIvo Barrow,ivo@y.example.test,support,too short\n"
    out = client.post("/api/applicants/csv", headers=h, content=csv.encode()).json()
    assert out["rejected"] == 2 and out["added"] == 0 and len(out["problems"]) == 2 and "email" in out["problems"][0]
    assert client.post("/api/applicants/csv", headers=h, content=b"name,role,resume_text\n ,support,x\n").status_code == 400  # a row with no name refuses the file


def test_an_empty_csv_is_refused_not_reported_as_done(client):
    h = H(client)
    for body in (b"", b"name,email,phone,role,resume_text,source,school\n"):
        r = client.post("/api/applicants/csv", headers=h, content=body)
        assert r.status_code == 400 and "no applicant rows" in r.json()["error"]["message"]


def test_showing_an_identity_is_written_to_the_audit_log_once_not_on_every_refresh(client):
    h = H(client)
    a = apps(client, h, stage="shortlisted")[0]
    for _ in range(4):
        assert client.get(f"/api/applications/{a['id']}", headers=h, params={"reveal": "true"}).status_code == 200
    log = [e for e in client.get("/api/audit", headers=h, params={"limit": 200}).json() if e["action"] == "identity.revealed" and e["target"] == f"application:{a['id']}"]
    assert len(log) == 1


def test_stored_times_say_utc_so_a_browser_does_not_read_them_as_local(client):
    h = H(client)
    ap = client.get("/api/approvals", headers=h).json()[0]
    assert ap["created_at"].endswith("+00:00")
    assert client.get("/api/audit", headers=h).json()[0]["at"].endswith("+00:00")
    client.post("/api/fairness/run", headers=h, json={"role": "all", "min_group": 10})
    assert client.get("/api/fairness", headers=h).json()["report"]["created_at"].endswith("+00:00")


def test_the_kill_switch_stops_an_invite_even_in_the_offline_demo(client):
    h = H(client)
    a = apps(client, h, stage="shortlisted")[0]
    iv = client.post(f"/api/applications/{a['id']}/interviews", headers=h, json={"interviewers": ["owner@example.test"], "starts_at": "2026-12-08T10:00:00Z"}).json()["id"]
    client.post("/api/settings", headers=h, json={"kill_switch": True})
    out = client.post(f"/api/interviews/{iv}/invite", headers=h, json={"confirm": True}).json()
    assert out["sent"] is False and "kill switch" in out["reason"]
    assert client.get(f"/api/interviews/{iv}", headers=h).json()["status"] == "planned"


def test_an_interview_cannot_be_planned_in_the_past(client):
    h = H(client)
    a = apps(client, h, stage="shortlisted")[0]
    r = client.post(f"/api/applications/{a['id']}/interviews", headers=h, json={"interviewers": ["owner@example.test"], "starts_at": "2020-01-08T10:00:00Z"})
    assert r.status_code == 400 and "past" in r.json()["error"]["message"]


def test_an_offer_approval_shows_the_terms_and_a_duplicate_name_is_explained_in_words(client):
    h = H(client)
    ap, offer = pending_offer(client, h)
    assert ap["offer"]["terms"] == offer["terms"] and ap["offer"]["title"] == offer["title"]
    role = client.post("/api/roles", headers=h, json={"title": "Warehouse Lead", "description": "Runs the day shift."}).json()
    rub = client.post(f"/api/roles/{role['id']}/rubric", headers=h, json={}).json()
    two = [{"id": "safety", "name": "Safety", "weight": 3, "anchors": {"1": "Has seen it done.", "3": "Does it alone.", "5": "Teaches others."}, "look_for": ["safety"]}] * 2
    client.put(f"/api/rubrics/{rub['id']}", headers=h, json={"criteria": two})
    problems = client.post(f"/api/rubrics/{rub['id']}/check", headers=h).json()["problems"]
    assert any("same name" in p for p in problems) and not any("id" in p.split(":")[1].split() for p in problems)


def test_the_new_routes_still_refuse_a_read_only_sign_in(tmp_path):
    c = TestClient(create_app(make_settings(tmp_path)))
    v = H(c, "viewer@example.test")
    assert c.post("/api/applicants/csv", headers=v, content=b"").status_code == 403


def test_a_second_role_with_the_same_title_is_refused(client):
    h = H(client)
    r = client.post("/api/roles", headers=h, json={"title": "data analyst", "description": "x"})
    assert r.status_code == 400 and "already a role called" in r.json()["error"]["message"]


def test_the_same_applicant_pasted_twice_without_an_email_is_a_duplicate(client):
    h = H(client)
    body = {"name": "Odalys Thorne", "role": "support", "resume_text": TEXT}
    assert client.post("/api/applicants", headers=h, json=body).json()["status"] == "added"
    assert client.post("/api/applicants", headers=h, json=body).json()["status"] == "duplicate"
    csv = "name,role,resume_text\nIvo Barrow,support,\"" + TEXT + "\"\n"
    assert client.post("/api/applicants/csv", headers=h, content=csv.encode()).json()["added"] == 1
    again = client.post("/api/applicants/csv", headers=h, content=csv.encode()).json()
    assert again["added"] == 0 and again["duplicate"] == 1


def test_someone_scored_under_an_earlier_rubric_keeps_that_score_on_screen_until_read_again(client):
    h = H(client)
    a = apps(client, h, stage="shortlisted")[0]
    before = client.get(f"/api/applications/{a['id']}", headers=h).json()
    assert before["score"] and before["rubric"]["version"] == before["current_version"] == 1
    role = next(r for r in client.get("/api/roles", headers=h).json() if r["key"] == a["role"])
    v2 = client.post(f"/api/roles/{role['id']}/rubric", headers=h, json={}).json()
    assert client.post(f"/api/rubrics/{v2['id']}/lock", headers=h).status_code == 200
    after = client.get(f"/api/applications/{a['id']}", headers=h).json()
    assert after["score"]["total"] == before["score"]["total"] and after["rubric"]["version"] == 1 and after["current_version"] == 2
    row = next(x for x in client.get("/api/applications", headers=h, params={"stage": "shortlisted"}).json() if x["id"] == a["id"])
    assert row["total"] == before["score"]["total"]
    assert client.post(f"/api/applications/{a['id']}/score", headers=h).status_code == 200
    again = client.get(f"/api/applications/{a['id']}", headers=h).json()
    assert again["rubric"]["version"] == 2


def test_an_illegal_move_is_explained_with_stage_names_a_person_reads(client):
    h = H(client)
    a = apps(client, h, stage="applied")[0]
    r = client.post(f"/api/applications/{a['id']}/move", headers=h, json={"to": "hired", "note": ""})
    assert r.status_code == 400 and r.json()["error"]["message"] == "From Applied you can move to Shortlisted, Declined or Withdrawn."


def test_a_resume_file_name_is_not_shown_while_identity_is_hidden(client):
    h = H(client)
    f = client.post("/api/applicants/file?role=support&name=Pell Raine", headers={**h, "x-filename": "pell-raine-cv.txt"}, content=TEXT.encode()).json()
    hidden = client.get(f"/api/applications/{f['application_id']}", headers=h).json()
    assert hidden["resume"]["filename"] == "resume file" and "pell" not in str(hidden).lower().replace("pell raine", "")
