"""Shared set up for the hardening tests: a real (not demo) install with two people who can sign in, and a few small recorders."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi.testclient import TestClient

from slatehire.api.app import create_app
from slatehire.config import Settings
from slatehire.context import Ctx
from slatehire.dbsetup import make_private_engine
from sendora_core import models as _core  # noqa: F401
from sendora_core.auth import hash_password
from sendora_core.db import Base, make_session_factory

ROOT = Path(__file__).resolve().parents[3]
REAL_SECRET = "test-only-Rt7Kq2Vw9Xm4Zc8Lb3Nf6Hy1Js5Dp0Ga2Ue7Tq4Wi9"
PASSWORD = "a-long-test-password-1"
OWNER = "sam@rivera.example.test"
APPROVER = "pat@rivera.example.test"
THIRD = "robin@rivera.example.test"
HOOK = "test-only-hook-secret"
IDENTITY = dict(owner_email=OWNER, company_name="Rivera Works")


@lru_cache(maxsize=1)
def pw_hash() -> str:
    return hash_password(PASSWORD)


def real_settings(tmp_path, **kw) -> Settings:
    """A real install: demo off, a real secret, an owner and an approver with real (test) passwords, its own database and export folder."""
    members = f'[{{"email": "{THIRD}", "password_hash": {_q(pw_hash())}, "role": "approver"}}]'
    base = dict(database_url=f"sqlite:///{tmp_path / 'r.sqlite3'}", export_dir=str(tmp_path / "exports"), demo_mode=False, session_secret=REAL_SECRET, owner_password_hash=pw_hash(),
                approver_email=APPROVER, approver_password_hash=pw_hash(), members_json=members, application_webhook_secret=HOOK, seed_dir="", _env_file=None, **IDENTITY)
    base.update(kw)
    return Settings(**base)


def _q(text: str) -> str:
    import json

    return json.dumps(text)


def real_ctx(tmp_path, **kw) -> Ctx:
    s = real_settings(tmp_path, **kw)
    engine = make_private_engine(s.database_url)
    Base.metadata.create_all(engine)
    return Ctx(s, make_session_factory(engine))


def real_client(tmp_path, **kw) -> TestClient:
    return TestClient(create_app(real_settings(tmp_path, **kw)), base_url="http://api.test")


def sign_in(client: TestClient, email: str = OWNER, password: str = PASSWORD) -> dict:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"x-session": r.json()["token"]}


class RecordingCalendar:
    """A connected calendar with the same write guard as the real adapters: it counts every invite that really went out."""

    name = "recording"

    def __init__(self, settings):
        self.s, self.sent = settings, []

    def create_event(self, *, title, starts_at, minutes, attendees, note, confirm):
        from sendora_core.safety import guard_write

        guard_write(self.s, "calendar.create_event")
        self.sent.append(attendees)
        return {"ref": f"rec-{len(self.sent)}", "detail": "Recorded."}

    def healthcheck(self):
        return True, "ok"


CRITERIA = [{"id": "writing", "name": "Writing to customers", "weight": 3, "anchors": {"1": "Has seen it done.", "3": "Has done it alone.", "5": "Has led it with results."}, "look_for": ["replies", "wrote"]},
            {"id": "tools", "name": "Support tools", "weight": 2, "anchors": {"1": "Has seen it done.", "3": "Has done it alone.", "5": "Has led it with results."}, "look_for": ["help desk", "ticket"]}]
RESUME = "Pat Quinn worked on the help desk for four years. I wrote replies to about 40 customer emails a day and cut the ticket backlog from 300 to 40 in one quarter."


def start_role(c, h, title: str = "Support Specialist") -> dict:
    """Create a role, give it a rubric and lock it, the way a person does in the app."""
    role = c.post("/api/roles", headers=h, json={"title": title, "team": "Support", "description": "Answers customers."})
    assert role.status_code == 200, role.text
    rub = c.post(f"/api/roles/{role.json()['id']}/rubric", headers=h, json={"criteria": CRITERIA})
    assert rub.status_code == 200, rub.text
    locked = c.post(f"/api/rubrics/{rub.json()['id']}/lock", headers=h)
    assert locked.status_code == 200, locked.text
    return role.json()


def get_to_offer(c, hs: dict, role_key: str, *, name: str = "Pat Quinn", email: str = "pat.quinn@mail.example.test") -> dict:
    """Paste one applicant and take them to a drafted offer: score, shortlist, interview, two scorecards from two different people, the offer terms written by the owner."""
    from datetime import date, timedelta

    h = hs["owner"]
    a = c.post("/api/applicants", headers=h, json={"name": name, "email": email, "role": role_key, "resume_text": RESUME})
    assert a.status_code == 200 and a.json()["status"] == "added", a.text
    app_id = a.json()["application_id"]
    assert c.post(f"/api/applications/{app_id}/score", headers=h).status_code == 200
    mv = c.post(f"/api/applications/{app_id}/move", headers=h, json={"to": "shortlisted", "note": "Strong evidence on the main criteria."})
    assert mv.status_code == 200, mv.text
    when = (date.today() + timedelta(days=5)).isoformat() + "T10:00:00+00:00"
    iv = c.post(f"/api/applications/{app_id}/interviews", headers=h, json={"interviewers": [APPROVER, THIRD], "starts_at": when, "minutes": 45})
    assert iv.status_code == 200, iv.text
    for who in ("approver", "third"):
        r = c.post(f"/api/interviews/{iv.json()['id']}/scorecards", headers=hs[who], json={"ratings": {"writing": 4, "tools": 3}, "comments": {}, "recommendation": "yes"})
        assert r.status_code == 200, r.text
    start = (date.today() + timedelta(days=40)).isoformat()
    o = c.post(f"/api/applications/{app_id}/offer", headers=h, json={"title": "Support Specialist", "start_date": start, "terms": "Full time, base pay as agreed in the interview, review after six months."})
    assert o.status_code == 200, o.text
    return {"app_id": app_id, "offer_id": o.json()["id"], "interview_id": iv.json()["id"]}


def three_people(c) -> dict:
    return {"owner": sign_in(c, OWNER), "approver": sign_in(c, APPROVER), "third": sign_in(c, THIRD)}
