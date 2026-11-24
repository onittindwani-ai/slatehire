from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from slatehire.adapters.ats import Ashby, Greenhouse, Workable
from slatehire.adapters.base import safe_base_url
from slatehire.adapters.calendar import CalCom, GoogleCalendar, SeedCalendar
from slatehire.adapters.fetch import safe_fetch
from slatehire.adapters.handoff import BreezedocHandoff, PackageHandoff
from slatehire.adapters.mailbox import ImapMailbox
from slatehire.config import Settings
from slatehire.ingest import from_email
from slatehire.registry import build_adapters, build_registry
from mock.mail_servers import FakeMailServers
from mock.vendor_mocks import AshbyMock, CalComMock, GoogleCalendarMock, GreenhouseMock, WorkableMock
from sendora_core.adapters import AdapterError
from sendora_core.safety import DraftModeError, KillSwitchError
from sendora_core.settings import Mode

WHEN = datetime(2026, 12, 4, 10, 0, tzinfo=timezone.utc)


def st(**kw) -> Settings:
    return Settings(mode=Mode.LIVE, demo_mode=False, session_secret="x" * 20, allow_http_local_targets=True, _env_file=None, **kw)


def tc(mock, base="http://testserver"):
    return TestClient(mock.app, base_url=base)


def test_ashby_pages_through_candidates_skips_do_not_contact_and_reads_the_resume():
    m = AshbyMock()
    got = Ashby(st(ashby_api_key=m.key), tc(m)).list_applicants()
    assert len(got) == 4 and all("replies to customer emails" in a.resume_text for a in got) and all(a.external_ref for a in got)
    with pytest.raises(AdapterError, match="refused"):
        Ashby(st(ashby_api_key="wrong"), tc(m)).list_applicants()


def test_workable_and_greenhouse_follow_their_paging_and_skip_disqualified():
    wm = WorkableMock()
    got = Workable(st(workable_token=wm.token, workable_subdomain="demo"), tc(wm, "http://testserver/spi/v3")).list_applicants()
    assert len(got) == 3 and all(a.resume_text for a in got)
    g = GreenhouseMock()
    rows = Greenhouse(st(greenhouse_token=g.token), tc(g)).list_applicants()
    assert [a.name for a in rows] == ["Fictional Hire1", "Fictional Hire2", "Fictional Hire3"]


def test_the_ats_adapters_are_read_only():
    for cls in (Ashby, Workable, Greenhouse):
        assert not [n for n in dir(cls) if n.startswith(("create", "update", "delete", "send", "write", "post_"))]


def test_calcom_and_google_send_only_when_live_confirmed_and_not_killed():
    m, g = CalComMock(), GoogleCalendarMock()
    c = CalCom(st(calcom_api_key=m.key, calcom_event_type_id=7), tc(m))
    out = c.create_event(title="T", starts_at=WHEN, minutes=45, attendees=["cand@mail.example.test", "i@example.test"], note="n", confirm=True)
    assert out["ref"] == "bk-1" and m.bookings[0]["lengthInMinutes"] == 45 and m.bookings[0]["guests"] == ["i@example.test"]
    gc = GoogleCalendar(st(google_access_token=g.token), tc(g))
    assert gc.create_event(title="T", starts_at=WHEN, minutes=30, attendees=["a@b.test"], note="n", confirm=True)["ref"] == "ev-1"
    for a in (c, gc):
        with pytest.raises(AdapterError, match="confirm"):
            a.create_event(title="T", starts_at=WHEN, minutes=30, attendees=["a@b.test"], note="n", confirm=False)
        a.s = a.s.model_copy(update={"mode": Mode.DRAFT})
        with pytest.raises(DraftModeError):
            a.create_event(title="T", starts_at=WHEN, minutes=30, attendees=["a@b.test"], note="n", confirm=True)
        a.s = a.s.model_copy(update={"mode": Mode.LIVE, "kill_switch": True})
        with pytest.raises(KillSwitchError):
            a.create_event(title="T", starts_at=WHEN, minutes=30, attendees=["a@b.test"], note="n", confirm=True)
    assert len(m.bookings) == 1 and len(g.events) == 1


def test_seed_calendar_and_package_handoff_stay_inside(tmp_path):
    assert "Nothing is sent" in SeedCalendar(st()).create_event(title="T", starts_at=WHEN, minutes=30, attendees=[], note="", confirm=True)["detail"]
    h = PackageHandoff(Settings(export_dir=str(tmp_path / "x"), _env_file=None))
    r = h.hand_off(offer_id=3, title="Support Specialist", candidate_code="C0001", body="text")
    assert (tmp_path / "x" / r["ref"]).read_text().startswith("text")
    with pytest.raises(AdapterError, match="not built"):
        BreezedocHandoff(st())


def test_imap_reads_unseen_application_emails_from_the_local_fake_server():
    with FakeMailServers() as servers:
        raw = (b"From: Fictional Applicant <fa@mail.example.test>\r\nSubject: Application for Customer Support Specialist\r\nMessage-ID: <m1@x>\r\n\r\n" + b"I wrote replies to customer emails every day and trained 3 colleagues at my last job.\r\n")
        servers.store.deliver(raw)
        mb = ImapMailbox(st(imap_host="127.0.0.1", imap_port=servers.imap_port, imap_user="demo", imap_password="demo-password", imap_use_ssl=False))
        ok, _ = mb.healthcheck()
        assert ok
        uid, data = mb.fetch_new()[0]
        a = from_email(data, {"support": "Customer Support Specialist"})
        assert a.role_key == "support" and a.email == "fa@mail.example.test"
        mb.mark_seen(uid)
        assert mb.fetch_new() == []


def test_ssrf_guard_refuses_private_addresses_and_odd_schemes():
    for url in ("http://127.0.0.1/x", "http://169.254.169.254/latest", "http://10.0.0.5/r", "file:///etc/passwd", "ftp://example.com/x", "https://user:pw@example.com/x", "http://localhost:8000/a"):
        with pytest.raises(AdapterError):
            safe_base_url(url)
        with pytest.raises(AdapterError):
            safe_fetch(url)


def test_registry_marks_tiers_and_demo_mode_only_builds_offline_adapters():
    reg = build_registry(st())
    tiers = {(r["category"], r["name"]): r["tier"] for r in reg.describe()}
    assert tiers[("ats", "seed")] == "A" and tiers[("ats", "ashby")] == "B" and tiers[("handoff", "breezedoc")] == "C"
    assert not any(r["live_verified"] for r in reg.describe())
    with pytest.raises(AdapterError, match="DEMO_MODE"):
        build_adapters(Settings(demo_mode=True, ats_adapter="ashby", ashby_api_key="k", session_secret="x" * 20, _env_file=None))
