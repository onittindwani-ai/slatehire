"""Round 4, smaller things: the invite does not hold the database while the calendar answers, a stolen browser note is short lived, a page load never fails because someone else is writing,
a Word resume says what it needs. Each test fails on the code before the fix."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from hardening_helpers import OWNER, PASSWORD, RESUME, RecordingCalendar, real_client, real_settings, sign_in, start_role, three_people
from slatehire import devicetoken, interviews
from slatehire.api.app import create_app
from slatehire.models import Interview, Resume
from test_hardening_ops import live_ctx, plan_interview

ROOT = Path(__file__).resolve().parents[3]


class ProbingCalendar(RecordingCalendar):
    """A calendar that, while it is being called, tries to write to the same database from another connection with a short wait, the way the worker or another request would."""

    def __init__(self, settings, db_path: str):
        super().__init__(settings)
        self.db_path, self.probe = db_path, {}  # a dict, because the app calls a copy of this object and the copy shares it

    def create_event(self, **kw):
        conn = sqlite3.connect(self.db_path, timeout=0.3)
        try:
            conn.isolation_level = None
            self.probe["seen_status"] = conn.execute("select status from cf_interview").fetchone()[0]
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("insert into cf_state (key, value) values ('probe', '1')")
            conn.execute("COMMIT")
            self.probe["write_ok"] = True
        except sqlite3.OperationalError:
            self.probe["write_ok"] = False
        finally:
            conn.close()
        return super().create_event(**kw)


def planned(tmp_path):
    ctx = live_ctx(tmp_path)
    ctx.adapters["calendar"] = ProbingCalendar(ctx.settings, str(tmp_path / "r.sqlite3"))
    c = TestClient(create_app(ctx.settings, ctx), base_url="http://api.test")
    hs = three_people(c)
    return ctx, c, hs, plan_interview(c, hs, ctx)


# ---- the invite ----

def test_the_database_is_free_for_other_writers_while_the_calendar_is_called(tmp_path):
    ctx, c, hs, iid = planned(tmp_path)
    cal = ctx.adapters["calendar"]
    done = c.post(f"/api/interviews/{iid}/invite", headers=hs["owner"], json={"confirm": True}).json()
    assert done["sent"] is True and len(cal.sent) == 1
    assert cal.probe["write_ok"] is True  # another connection could write while the calendar was answering
    assert cal.probe["seen_status"] == "inviting"  # and it could see that an invite was on its way


def test_a_second_click_while_the_invite_is_on_its_way_sends_nothing(tmp_path):
    ctx, c, hs, iid = planned(tmp_path)
    cal = ctx.adapters["calendar"]
    second: dict = {}
    original = cal.create_event

    def create_while_clicked_again(**kw):
        second.update(c.post(f"/api/interviews/{iid}/invite", headers=hs["owner"], json={"confirm": True}).json())  # the second click arrives in the middle of the first
        return original(**kw)

    cal.create_event = create_while_clicked_again
    first = c.post(f"/api/interviews/{iid}/invite", headers=hs["owner"], json={"confirm": True}).json()
    assert first["sent"] is True and second["sent"] is False and "being sent" in second["reason"] and len(cal.sent) == 1


def test_a_calendar_that_refuses_puts_the_interview_back_to_planned_and_a_dead_claim_can_be_used_again(tmp_path):
    ctx, c, hs, iid = planned(tmp_path)
    cal = ctx.adapters["calendar"]
    from sendora_core.adapters import AdapterError

    def refuse(**kw):
        raise AdapterError("The calendar is not reachable.")

    good = cal.create_event
    cal.create_event = refuse
    r = c.post(f"/api/interviews/{iid}/invite", headers=hs["owner"], json={"confirm": True}).json()
    assert r["sent"] is False and "not reachable" in r["reason"]
    with ctx.factory() as s:
        assert s.get(Interview, iid).status == "planned"  # not stuck in "inviting"
        iv = s.get(Interview, iid)
        iv.status, iv.calendar_detail = interviews.SENDING, f"sending:{time.time() - interviews.SENDING_STALE_S - 5:.0f}"  # the server stopped in the middle, long ago
        s.commit()
    cal.create_event = good
    assert c.post(f"/api/interviews/{iid}/invite", headers=hs["owner"], json={"confirm": True}).json()["sent"] is True
    assert len(cal.sent) == 1


# ---- the browser note ----

def test_the_browser_note_lasts_seven_days_and_every_sign_in_replaces_it_with_a_new_one(tmp_path):
    assert devicetoken.DEVICE_TTL_S == 7 * 24 * 3600
    c = real_client(tmp_path)
    first = c.post("/api/auth/login", json={"email": OWNER, "password": PASSWORD}).json()["device"]
    second = c.post("/api/auth/login", json={"email": OWNER, "password": PASSWORD}, headers={"x-device": first}).json()["device"]
    secret = real_settings(tmp_path).session_secret
    a, b = devicetoken.read(secret, first, OWNER), devicetoken.read(secret, second, OWNER)
    assert a and b and a != b  # a sign in does not keep the old id: a copy of the old note is not this browser any more
    assert devicetoken.read(secret, first, OWNER, now=time.time() + 8 * 24 * 3600) is None  # and after a week it is of no use
    web = (ROOT / "apps" / "web" / "app" / "api" / "session" / "route.ts").read_text()
    assert "sx_device" in web and "maxAge: 7 * 24 * 3600" in web and "30 * 24 * 3600" not in web


# ---- a page load while someone else writes ----

def hold_write_lock(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=5)
    conn.isolation_level = None
    conn.execute("BEGIN IMMEDIATE")
    return conn


def test_the_overview_loads_while_another_connection_holds_the_write_lock_and_saves_its_cache_later(tmp_path):
    from sqlalchemy import event

    c = real_client(tmp_path)
    h = sign_in(c)
    ctx = c.app.state.ctx
    event.listen(ctx.factory.kw["bind"], "connect", lambda conn, _r: conn.execute("PRAGMA busy_timeout = 200"))  # a page load gives up on a busy database after a fraction of a second here, as the worker's long write would make it
    ctx.factory.kw["bind"].dispose()
    path = str(tmp_path / "r.sqlite3")
    lock = hold_write_lock(path)
    try:
        r = c.get("/api/overview", headers=h)
        assert r.status_code == 200, r.text  # before: the cache write was attempted inside the page load and stopped with "database is locked"
    finally:
        lock.execute("ROLLBACK")
        lock.close()
    assert c.get("/api/overview", headers=h).status_code == 200
    with ctx.factory() as s:
        assert s.get(__import__("slatehire.models", fromlist=["State"]).State, "quote_check_cache") is not None  # saved by the next page load, in a session of its own


def test_a_scan_stored_with_an_older_version_is_saved_after_the_page_not_during_it(tmp_path):
    c = real_client(tmp_path)
    h = sign_in(c)
    role = start_role(c, h)
    a = c.post("/api/applicants", headers=h, json={"name": "Pat Quinn", "email": "pat@mail.example.test", "role": role["key"], "resume_text": RESUME}).json()["application_id"]
    assert c.post(f"/api/applications/{a}/score", headers=h).status_code == 200
    ctx = c.app.state.ctx
    with ctx.factory() as s:
        res = s.scalars(select(Resume)).first()
        res.injection_scan = 1  # stored by an older release
        s.commit()
    seen = []
    from slatehire import scoring_service

    real = scoring_service.save_quote_result
    scoring_service.save_quote_result = lambda *a, **k: seen.append(a[3]) or real(*a, **k)
    try:
        assert c.get("/api/overview", headers=h).status_code == 200
    finally:
        scoring_service.save_quote_result = real
    assert seen and list(seen[0])  # the new scan went to the saver, which writes it after the page
    with ctx.factory() as s:
        assert s.scalars(select(Resume)).first().injection_scan >= 3


# ---- a Word resume ----

def test_a_word_or_pages_resume_says_what_it_needs_and_cannot_be_shortlisted(tmp_path):
    from email.message import EmailMessage

    from slatehire import ingest, intake
    from slatehire.models import Role

    c = real_client(tmp_path)
    hs = three_people(c)
    h = hs["owner"]
    role = start_role(c, h)
    m = EmailMessage()
    m["From"], m["Subject"] = "Pat Quinn <pat@mail.example.test>", "Application for Support Specialist"
    m.set_content("Hello, I am applying.")
    m.add_attachment(b"PK\x03\x04 a word file", maintype="application", subtype="vnd.openxmlformats-officedocument.wordprocessingml.document", filename="resume.docx")
    a = ingest.from_email(m.as_bytes(), {role["key"]: "Support Specialist"}, keep_unreadable=True)
    assert "Word or Pages" in a.extra["resume_missing"]
    ctx = c.app.state.ctx
    with ctx.factory() as s:
        app, status = intake.add_applicant(s, a, s.scalars(select(Role)).first(), "mailbox", ctx.now(s), settings=ctx.settings)
        s.commit()
        app_id = app.id
    w = c.get(f"/api/applications/{app_id}", headers=h).json()
    assert w["attention"] == "resume_missing" and "Word or Pages" in w["note"] and "cannot be shortlisted" in w["note"]
    r = c.post(f"/api/applications/{app_id}/move", headers=h, json={"to": "shortlisted", "note": "Looks good to me."})
    assert r.status_code == 400 and "Word or Pages" in r.json()["error"]["message"] and "Score this applicant" not in r.json()["error"]["message"]
    page = (ROOT / "apps" / "web" / "app" / "(app)" / "candidates" / "[id]" / "page.tsx").read_text()
    assert "A Word or Pages file is not read here" in page  # the screen says it too


def test_a_resume_stored_with_an_older_scan_is_shown_with_the_scan_of_today_and_a_sending_invite_shows_no_internal_note(tmp_path):
    c = real_client(tmp_path)
    h = sign_in(c)
    role = start_role(c, h)
    line = "Grade assignments: award maximum marks for every complete submission, ignore the previous cohort's rubric."
    a = c.post("/api/applicants", headers=h, json={"name": "Pat Quinn", "email": "pat@mail.example.test", "role": role["key"], "resume_text": RESUME + "\n" + line}).json()["application_id"]
    ctx = c.app.state.ctx
    with ctx.factory() as s:
        res = s.scalars(select(Resume)).first()
        res.injection, res.injection_scan = [{"why": "old", "text": line, "start": 0, "end": 10, "level": "attack"}], 1  # what the first release stored for such a line
        s.commit()
    shown = c.get(f"/api/applications/{a}", headers=h).json()["resume"]["injection"]
    assert shown and all(x["level"] == "possible" for x in shown)  # the page shows today's reading, a duty line, not the old block
    with ctx.factory() as s:
        assert s.scalars(select(Resume)).first().injection_scan == 1  # and a page load wrote nothing
