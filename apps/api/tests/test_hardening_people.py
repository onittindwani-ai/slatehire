"""Offers need two different people, deleting a person really deletes them, the fairness page shows no small group, and what a name or a rubric may hold."""

import json
from datetime import timedelta

from sqlalchemy import select

from hardening_helpers import HOOK, OWNER, RESUME, THIRD, get_to_offer, real_client, real_ctx, start_role, three_people
from slatehire import fairness_service, pipeline, retention, rubric_service
from slatehire.config import Settings
from slatehire.models import Application, Candidate, Demographic, IntakeLog, Offer, Resume
from sendora_core.audit import record_audit  # noqa: F401
from sendora_core.models import AuditEntry


# ---- M6: the person who wrote the terms cannot approve them ----

def offer_ready(tmp_path):
    c = real_client(tmp_path)
    hs = three_people(c)
    role = start_role(c, hs["owner"])
    return c, hs, get_to_offer(c, hs, role["key"])


def test_the_person_who_wrote_the_terms_cannot_approve_them_even_when_a_colleague_asked(tmp_path):
    c, hs, flow = offer_ready(tmp_path)
    assert c.post(f"/api/offers/{flow['offer_id']}/request-approval", headers=hs["approver"]).status_code == 200  # a colleague clicks Ask for approval, as a favour
    approval = next(a for a in c.get("/api/approvals", headers=hs["owner"]).json() if a["status"] == "pending")
    refused = c.post(f"/api/approvals/{approval['id']}/decide", headers=hs["owner"], json={"approve": True})  # the owner wrote the terms
    assert refused.status_code == 403 and "wrote these terms" in refused.text
    assert next(o for o in c.get("/api/offers", headers=hs["owner"]).json() if o["id"] == flow["offer_id"])["status"] == "pending_approval"
    assert c.post(f"/api/approvals/{approval['id']}/decide", headers=hs["approver"], json={"approve": True}).status_code == 409  # the one who asked is refused by the base
    assert c.post(f"/api/approvals/{approval['id']}/decide", headers=hs["third"], json={"approve": True}).json() == {"status": "approved"}  # a third person decides


def test_the_author_who_asks_for_approval_themselves_is_still_refused(tmp_path):
    c, hs, flow = offer_ready(tmp_path)
    c.post(f"/api/offers/{flow['offer_id']}/request-approval", headers=hs["owner"])
    approval = next(a for a in c.get("/api/approvals", headers=hs["owner"]).json() if a["status"] == "pending")
    assert c.post(f"/api/approvals/{approval['id']}/decide", headers=hs["owner"], json={"approve": True}).status_code == 409
    assert c.post(f"/api/approvals/{approval['id']}/decide", headers=hs["approver"], json={"approve": True}).json() == {"status": "approved"}


# ---- M9: a name cannot add a paragraph to an offer ----

def test_a_name_with_line_breaks_cannot_add_terms_to_the_offer_file(tmp_path):
    c = real_client(tmp_path)
    hs = three_people(c)
    role = start_role(c, hs["owner"])
    evil = "Jane Doe\n\nAdditional terms: a signing bonus of 50,000.\r\nTo: someone else"
    flow = get_to_offer(c, hs, role["key"], name=evil, email="jane@mail.example.test")
    o = next(x for x in c.get("/api/offers", headers=hs["owner"]).json() if x["id"] == flow["offer_id"])
    to_lines = [ln for ln in o["body"].splitlines() if ln.startswith("To:")]
    assert len(to_lines) == 1 and "\n" not in o["name"] and "Additional terms" in to_lines[0]  # the words are on the one To line, not a paragraph of their own
    assert o["body"].count("signing bonus") == 1 and "\n\nAdditional terms" not in o["body"]


def test_every_way_in_cleans_a_name_the_same_way(tmp_path):
    import hashlib
    import hmac

    c = real_client(tmp_path)
    hs = three_people(c)
    role = start_role(c, hs["owner"])
    body = json.dumps({"name": "Kim\nLee\u0000 ", "email": "kim@mail.example.test", "role": role["key"], "resume_text": RESUME}).encode()
    sig = hmac.new(HOOK.encode(), body, hashlib.sha256).hexdigest()
    assert c.post("/api/webhooks/application", content=body, headers={"x-signature": sig}).json()["status"] == "added"
    with c.app.state.ctx.factory() as s:
        assert [x.full_name for x in s.scalars(select(Candidate))] == ["Kim Lee"]  # the line break and the NUL byte are gone


# ---- M7: deleting a person ----

def declined_after_hand_off(tmp_path):
    ctx = real_ctx(tmp_path)
    from fastapi.testclient import TestClient

    from slatehire.api.app import create_app

    c = TestClient(create_app(ctx.settings, ctx), base_url="http://api.test")
    hs = three_people(c)
    role = start_role(c, hs["owner"])
    flow = get_to_offer(c, hs, role["key"], name="Grace Hopper", email="grace@mail.example.test")
    c.post(f"/api/offers/{flow['offer_id']}/request-approval", headers=hs["approver"])
    approval = next(a for a in c.get("/api/approvals", headers=hs["owner"]).json() if a["status"] == "pending")
    assert c.post(f"/api/approvals/{approval['id']}/decide", headers=hs["third"], json={"approve": True}).status_code == 200
    assert c.post(f"/api/offers/{flow['offer_id']}/hand-off", headers=hs["owner"]).status_code == 200
    return ctx, c, hs, flow


def test_the_sweep_rewrites_the_offer_file_of_a_person_who_declined_after_it_was_written(tmp_path):
    ctx, c, hs, flow = declined_after_hand_off(tmp_path)
    file = next((tmp_path / "exports").glob("offer-*.txt"))
    assert "Grace Hopper" in file.read_text()
    with ctx.factory() as s:
        app = s.get(Application, flow["app_id"])
        app.history = [*app.history, {"stage": "declined", "by": OWNER, "at": "2026-01-01T00:00:00+00:00", "note": "Grace took another job, Grace wrote to say so."}]
        app.stage, app.decision_note = "declined", "Grace took another job."
        app.updated_at = ctx.now(s) - timedelta(days=400)
        record_audit(s, OWNER, "x.test", None, {})
        s.commit()
    with ctx.factory() as s:
        assert retention.sweep(s, ctx.now(s), 365, export_dir=ctx.settings.export_dir) == 1
        s.commit()
    text = file.read_text()
    assert "Grace" not in text and "Hopper" not in text and "(deleted)" in text and "OFFER OF EMPLOYMENT" in text
    with ctx.factory() as s:
        app = s.get(Application, flow["app_id"])
        assert app.decision_note == "" and all(h["note"] == "" for h in app.history) and app.note == ""
        offer = s.scalars(select(Offer)).first()
        assert "Grace" not in offer.body and "Grace" not in offer.terms


def test_delete_on_request_does_the_same_through_the_api(tmp_path):
    ctx, c, hs, flow = declined_after_hand_off(tmp_path)
    file = next((tmp_path / "exports").glob("offer-*.txt"))
    assert c.delete(f"/api/candidates/{flow['app_id']}", headers=hs["owner"]).json() == {"ok": True}
    assert "Hopper" not in file.read_text()
    assert c.delete(f"/api/candidates/{flow['app_id']}", headers=hs["approver"]).status_code == 403


def test_the_intake_list_and_the_audit_log_keep_nothing_that_names_a_deleted_person(tmp_path):
    ctx, c, hs, flow = declined_after_hand_off(tmp_path)
    with ctx.factory() as s:
        s.add(IntakeLog(source="email", ref="grace@mail.example.test", status="duplicate", detail="Already applied for this role.", created_at=ctx.now(s)))
        s.add(IntakeLog(source="email", ref="someone.else@mail.example.test", status="rejected", detail="x", created_at=ctx.now(s)))
        s.add(IntakeLog(source="email", ref="old.person@mail.example.test", status="rejected", detail="x", created_at=ctx.now(s) - timedelta(days=500)))
        s.commit()
    assert c.post(f"/api/applications/{flow['app_id']}/move", headers=hs["owner"], json={"to": "declined", "note": "A private note about Grace and her family."}).status_code == 200
    assert c.delete(f"/api/candidates/{flow['app_id']}", headers=hs["owner"]).status_code == 200
    with ctx.factory() as s:
        refs = sorted(r.ref for r in s.scalars(select(IntakeLog)))
        assert "grace@mail.example.test" not in refs and "someone.else@mail.example.test" in refs
        assert not any("private note" in json.dumps(a.detail) for a in s.scalars(select(AuditEntry)))  # the append only log never held the words
        assert retention.sweep(s, ctx.now(s), 365) == 0
        assert "old.person@mail.example.test" not in [r.ref for r in s.scalars(select(IntakeLog))]  # the intake list ages out with the retention days


def test_people_nobody_decided_on_are_deleted_after_the_open_retention_days_and_never_when_it_is_zero(tmp_path):
    ctx = real_ctx(tmp_path, open_retention_days=730)
    from fastapi.testclient import TestClient

    from slatehire.api.app import create_app

    c = TestClient(create_app(ctx.settings, ctx), base_url="http://api.test")
    hs = three_people(c)
    role = start_role(c, hs["owner"])
    a = c.post("/api/applicants", headers=hs["owner"], json={"name": "Old Timer", "email": "old@mail.example.test", "role": role["key"], "resume_text": RESUME}).json()["application_id"]
    with ctx.factory() as s:
        s.get(Application, a).updated_at = ctx.now(s) - timedelta(days=800)
        s.commit()
    with ctx.factory() as s:
        assert retention.sweep(s, ctx.now(s), 365, open_days=0) == 0  # off
        assert retention.sweep(s, ctx.now(s), 365, open_days=900) == 0  # not old enough
        assert retention.sweep(s, ctx.now(s), 365, open_days=730) == 1
        s.commit()
        cand = s.scalars(select(Candidate)).first()
        assert cand.full_name == "(deleted)" and s.scalars(select(Resume)).first() is None


def test_a_deleted_person_gets_no_new_label(tmp_path):
    ctx, c, hs, flow = declined_after_hand_off(tmp_path)
    c.delete(f"/api/candidates/{flow['app_id']}", headers=hs["owner"])
    with ctx.factory() as s:
        code = s.scalars(select(Candidate)).first().code
        assert fairness_service.set_labels(s, {code: "B"}, OWNER) == {"set": 0, "unknown": 1}
        assert s.scalars(select(Demographic)).first() is None


# ---- M8: fairness ----

def test_the_fairness_run_is_owner_only_and_cannot_go_below_the_floor(tmp_path):
    c = real_client(tmp_path, fairness_min_group=10)
    hs = three_people(c)
    assert c.post("/api/fairness/run", headers=hs["approver"], json={"role": "all", "min_group": 2}).status_code == 403
    r = c.post("/api/fairness/run", headers=hs["owner"], json={"role": "all", "min_group": 2})
    assert r.status_code == 200 and r.json()["min_group"] == 10  # asked for 2, got the floor
    assert c.post("/api/fairness/run", headers=hs["owner"], json={"role": "all", "min_group": 40}).json()["min_group"] == 40  # larger is fine
    assert c.post("/api/fairness/run", headers=hs["owner"], json={"role": "all"}).json()["min_group"] == 10  # empty means the setting


def test_a_group_below_the_minimum_shows_no_counts_and_an_older_flagged_report_is_not_buried(world):
    from fastapi.testclient import TestClient

    from slatehire.api.app import create_app
    from conftest import login

    with world.factory() as s:
        first = fairness_service.run(s, OWNER, "all", 10)
        groups = first.payload["stages"]["shortlisted"]["groups"]
        small = [g for g in groups.values() if g["status"] == "too_few"]
        assert all(g["entered"] is None and g["selected"] is None and g["rate_pct"] is None and g["fewer_than"] == 10 for g in small)
        s.commit()
    c = TestClient(create_app(world.settings, world))
    h = login(c)
    body = c.get("/api/fairness", headers=h).json()
    assert body["min_group_floor"] == world.settings.fairness_min_group and body["report"]["id"]
    with world.factory() as s:  # a newer report with nothing flagged comes after
        newer = fairness_service.run(s, OWNER, "all", 200)
        newer.payload = {**newer.payload, "flagged": []}
        older = s.scalars(select(type(newer)).where(type(newer).id == body["report"]["id"])).first()
        older.payload = {**older.payload, "flagged": [["hired", "B"]]}
        s.commit()
    got = c.get("/api/fairness", headers=h).json()
    assert got["latest_flagged"] is not None and got["latest_flagged"]["id"] == body["report"]["id"] and got["report"]["id"] != body["report"]["id"]


# ---- L10, L11, L12 ----

def test_the_source_is_a_known_channel_while_identity_is_hidden(world):
    from fastapi.testclient import TestClient

    from slatehire.api.app import create_app
    from conftest import login

    with world.factory() as s:
        cand = s.scalars(select(Candidate).join(Application, Application.candidate_id == Candidate.id).where(Application.stage == "applied")).first()
        cand.source = "Stanford career fair, referral from Jo"
        code = cand.code
        s.commit()
    c = TestClient(create_app(world.settings, world))
    h = login(c)
    row = next(r for r in c.get("/api/applications", headers=h).json() if r["code"] == code)
    assert row["hidden"] and row["source"] == "other"
    ws = c.get(f"/api/applications/{row['id']}", headers=h).json()
    assert ws["person"]["source"] == "other"
    revealed = c.get(f"/api/applications/{row['id']}", headers=h, params={"reveal": "true"}).json()
    assert revealed["person"]["source"].startswith("Stanford") is (not revealed["blind"]["enforced"])


def test_a_reference_from_one_source_never_suppresses_an_applicant_from_another(tmp_path):
    from slatehire import intake
    from slatehire.ingest import Applicant

    ctx = real_ctx(tmp_path)
    with ctx.factory() as s:
        role = rubric_service.create_role(s, OWNER, "Support Specialist", "S", "d", key="support")
        now = ctx.now(s)
        text = RESUME
        assert intake.add_applicant(s, Applicant("Ann Ash", "ann@mail.example.test", "", "support", text, "", "email", external_ref="12345"), role, "mailbox", now, settings=ctx.settings)[1] == "added"
        assert intake.add_applicant(s, Applicant("Bea Birch", "bea@mail.example.test", "", "support", text + " More.", "", "greenhouse", external_ref="12345"), role, "ats", now, settings=ctx.settings)[1] == "added"
        assert intake.add_applicant(s, Applicant("Ann Ash", "ann@mail.example.test", "", "support", text, "", "email", external_ref="12345"), role, "mailbox", now, settings=ctx.settings)[1] == "duplicate"
        rows = "name,email,role,resume_text,code\nCy Cedar,cy@mail.example.test,support," + RESUME + " Different.,A001\nDee Dune,dee@mail.example.test,support," + RESUME + " Another.,A001\n"
        from slatehire.ingest import from_csv

        got = from_csv(rows.encode())
        assert all(a.external_ref is None for a in got)
        assert [intake.add_applicant(s, a, role, OWNER, now, settings=ctx.settings)[1] for a in got] == ["added", "added"]


def test_only_the_owner_turns_blind_mode_off_and_a_rubric_cannot_look_for_a_proxy(tmp_path):
    c = real_client(tmp_path)
    hs = three_people(c)
    role = start_role(c, hs["owner"], "Analyst")
    assert c.post(f"/api/roles/{role['id']}/rubric", headers=hs["approver"], json={"blind": False}).status_code == 403
    r = c.post(f"/api/roles/{role['id']}/rubric", headers=hs["owner"], json={"blind": False})
    assert r.status_code == 200 and r.json()["blind"] is False
    bad = [{"id": "fit", "name": "Culture fit", "weight": 3, "anchors": {"1": "Has seen it done.", "3": "Has done it alone.", "5": "Has led it with results."}, "look_for": ["young", "energetic", "native speaker"]},
           {"id": "ok", "name": "Writing", "weight": 3, "anchors": {"1": "Has seen it done.", "3": "Has done it alone.", "5": "Has led it with results."}, "look_for": ["wrote"]}]
    c.put(f"/api/rubrics/{r.json()['id']}", headers=hs["owner"], json={"criteria": bad})
    refused = c.post(f"/api/rubrics/{r.json()['id']}/lock", headers=hs["owner"])
    assert refused.status_code == 400 and "can stand in for age" in refused.text
    too_long = {**bad[1], "look_for": ["x" * 81]}
    assert c.put(f"/api/rubrics/{r.json()['id']}", headers=hs["owner"], json={"criteria": [too_long]}).status_code == 422
    assert c.put(f"/api/rubrics/{r.json()['id']}", headers=hs["owner"], json={"criteria": [{**bad[1], "look_for": ["w"] * 41}]}).status_code == 422


def test_the_settings_can_add_words_a_rubric_may_not_look_for():
    from slatehire import rubrics

    crit = [{"id": "a", "name": "Kitchen skill", "weight": 3, "anchors": {"1": "x" * 9, "3": "y" * 9, "5": "z" * 9}, "look_for": ["sous chef"]}]
    assert rubrics.proxy_problems(crit) == []
    assert rubrics.proxy_problems(crit, ["sous chef"]) and Settings(proxy_terms=" Sous Chef, ,Pastry ", _env_file=None).proxy_term_list() == ["sous chef", "pastry"]
    assert rubrics.proxy_problems([{"id": "a", "name": "Accenture work", "look_for": ["accenture"], "anchors": {}}]) == []  # whole words only: Accenture is not "accent"
    assert rubrics.proxy_problems([{"id": "a", "name": "x", "look_for": ["pregnancy"], "anchors": {}}])


# ---- L1: the move takes turns ----

def test_the_number_for_a_new_candidate_code_comes_from_the_highest_id(tmp_path):
    from slatehire import intake

    ctx = real_ctx(tmp_path)
    with ctx.factory() as s:
        assert intake.next_code(s) == "C0001"
        s.add(Candidate(code="C0001", full_name="A A", created_at=ctx.now(s)))
        s.flush()
        assert intake.next_code(s) == "C0002" and pipeline  # pipeline imported for the move test below
