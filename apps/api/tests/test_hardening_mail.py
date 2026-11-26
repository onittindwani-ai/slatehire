"""Mail intake: nothing is marked read before it is stored, one broken message loses no other, every message not added says why, and the connection is checked."""

import datetime as dt
import socket
import ssl
import threading
from email.message import EmailMessage

import pytest
from sqlalchemy import func, select

from hardening_helpers import real_ctx
from slatehire import jobs, rubric_service
from slatehire.adapters import mailbox as mailbox_mod
from slatehire.adapters.mailbox import ImapMailbox
from slatehire.ingest import MISSING_RESUME
from slatehire.models import Application, Candidate, IntakeLog, Role
from mock.mail_servers import StubMailServers
from sendora_core.adapters import AdapterError

GOOD = "Wrote replies to customer emails every day and trained three colleagues on the help desk tools at my last job.\n"
CRITERIA = [{"id": "c1", "name": "Writing", "weight": 3, "anchors": {"1": "Has seen it done.", "3": "Has done it alone.", "5": "Has led it with results."}, "look_for": ["replies"]},
            {"id": "c2", "name": "Tools", "weight": 3, "anchors": {"1": "Has seen it done.", "3": "Has done it alone.", "5": "Has led it with results."}, "look_for": ["help desk"]}]


def mail(sender: str, subject: str, body: str = GOOD, *, message_id: str = "", charset: str = "") -> bytes:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = sender, "jobs@rivera.example.test", subject
    if message_id:
        m["Message-ID"] = message_id
    m.set_content(body)
    raw = m.as_bytes()
    return raw.replace(b'charset="utf-8"', f'charset="{charset}"'.encode()) if charset else raw


def raw_bogus_charset(sender: str, subject: str) -> bytes:
    return (f"From: {sender}\r\nSubject: {subject}\r\nContent-Type: text/plain; charset=\"x-bogus\"\r\nContent-Transfer-Encoding: 8bit\r\n\r\n" + GOOD).encode()


def installed(tmp_path, srv):
    ctx = real_ctx(tmp_path, mailbox_adapter="imap", imap_host=srv.host, imap_port=srv.imap_port, imap_user="demo", imap_password="demo-password", imap_use_ssl=False)
    with ctx.factory() as s:
        role = rubric_service.create_role(s, "sam@rivera.example.test", "Customer Support Specialist", "Support", "Answers customers.", key="support")
        rub = rubric_service.new_draft(s, role, "sam@rivera.example.test", CRITERIA, True)
        rubric_service.lock(s, rub, "sam@rivera.example.test", ctx.now(s))
        s.commit()
    return ctx


def run(ctx) -> dict:
    with ctx.factory() as s:
        out = jobs.job_mailbox(s, ctx)
        s.commit()
        return out


def count(ctx, model) -> int:
    with ctx.factory() as s:
        return s.scalar(select(func.count()).select_from(model))


def log_rows(ctx) -> list[IntakeLog]:
    with ctx.factory() as s:
        return list(s.scalars(select(IntakeLog).order_by(IntakeLog.id)))


# ---- the read mark ----

def test_reading_a_message_does_not_mark_it_read(tmp_path):
    with StubMailServers() as srv:
        srv.store.deliver(mail("Ann <ann@mail.example.test>", "Application for Customer Support Specialist"))
        mb = ImapMailbox(real_ctx(tmp_path, mailbox_adapter="imap", imap_host=srv.host, imap_port=srv.imap_port, imap_user="demo", imap_password="demo-password", imap_use_ssl=False).settings)
        got = mb.fetch_new()
        assert len(got) == 1 and srv.store.inbox[0]["seen"] is False  # BODY.PEEK[]: the mark is the caller's to set
        assert len(mb.fetch_new()) == 1
        mb.mark_seen_many([u for u, _ in got])
        assert srv.store.inbox[0]["seen"] is True and mb.fetch_new() == []


def test_the_mock_server_marks_a_message_read_when_it_is_fetched_the_old_way(tmp_path):
    """The proof that the test above can fail: RFC 3501 says fetching RFC822 sets the seen flag, and the mock server now does the same."""
    import imaplib

    with StubMailServers() as srv:
        srv.store.deliver(mail("Ann <ann@mail.example.test>", "Application for Customer Support Specialist"))
        m = imaplib.IMAP4(srv.host, srv.imap_port)
        m.login("demo", "demo-password")
        m.select("INBOX")
        m.uid("FETCH", "1", "(RFC822)")
        m.logout()
        assert srv.store.inbox[0]["seen"] is True


def test_one_broken_email_loses_no_other_application_and_everything_is_marked_read_only_after_it_is_stored(tmp_path):
    with StubMailServers() as srv:
        ctx = installed(tmp_path, srv)
        long_id = "<" + "x" * 300 + "@mail.example.test>"
        srv.store.deliver(mail("Ann <ann@mail.example.test>", "Application for Customer Support Specialist", message_id="<a1@x>"))
        srv.store.deliver(raw_bogus_charset("Bad <bad@mail.example.test>", "Application for Customer Support Specialist"))  # an unknown character set
        srv.store.deliver(mail("Bo " + "B" * 300 + " <bo@mail.example.test>", "Application for Customer Support Specialist", message_id=long_id))  # an over long name and Message-ID
        srv.store.deliver(mail("Cy <cy@mail.example.test>", "Application for Customer Support Specialist", message_id="<c1@x>"))
        seen_during: list[int] = []
        real = ImapMailbox.mark_seen_many

        def spy(self, uids):
            seen_during.append(count(ctx, Candidate))  # what a second connection can see at the moment the messages are marked
            return real(self, uids)

        ImapMailbox.mark_seen_many = spy
        try:
            out = run(ctx)
        finally:
            ImapMailbox.mark_seen_many = real
        assert out["added"] == 4 and out["rejected"] == 0  # the unknown character set is read as text; the long values are cut or hashed
        assert seen_during == [4]  # all four applicants were already committed when the read marks were set
        assert all(m["seen"] for m in srv.store.inbox)
        with ctx.factory() as s:
            names = sorted(c.full_name for c in s.scalars(select(Candidate)))
            assert len(names) == 4 and all(len(n) <= 200 for n in names)
            assert all(len(c.external_ref or "") <= 120 for c in s.scalars(select(Candidate)))


def test_a_message_that_fails_inside_is_rolled_back_alone_and_written_to_the_list(tmp_path, monkeypatch):
    with StubMailServers() as srv:
        ctx = installed(tmp_path, srv)
        for who in ("ann", "bad", "cy"):
            srv.store.deliver(mail(f"{who.title()} <{who}@mail.example.test>", "Application for Customer Support Specialist", message_id=f"<{who}@x>"))
        real = jobs.intake.add_applicant

        def flaky(s, a, role, actor, now, **kw):
            if a.email == "bad@mail.example.test":
                s.add(Candidate(code="BOOM", full_name="x" * 5, created_at=now))
                s.flush()
                raise RuntimeError("the database refused a value: SECRET resume words")
            return real(s, a, role, actor, now, **kw)

        monkeypatch.setattr(jobs.intake, "add_applicant", flaky)
        out = run(ctx)
        assert out["added"] == 2 and out["rejected"] == 1
        with ctx.factory() as s:
            assert sorted(c.email for c in s.scalars(select(Candidate))) == ["ann@mail.example.test", "cy@mail.example.test"]  # the half written row of the bad one is gone
        rows = [r for r in log_rows(ctx) if r.status == "rejected"]
        assert len(rows) == 1 and rows[0].ref == "bad@mail.example.test" and "RuntimeError" in rows[0].detail and "SECRET" not in rows[0].detail
        assert all(m["seen"] for m in srv.store.inbox)  # the failure is on the list, so it is not fetched again and again


def test_nothing_is_marked_read_when_the_save_fails(tmp_path, monkeypatch):
    with StubMailServers() as srv:
        ctx = installed(tmp_path, srv)
        srv.store.deliver(mail("Ann <ann@mail.example.test>", "Application for Customer Support Specialist"))
        with ctx.factory() as s:
            monkeypatch.setattr(s, "commit", lambda: (_ for _ in ()).throw(RuntimeError("disk full")))
            with pytest.raises(RuntimeError):
                jobs.job_mailbox(s, ctx)
        assert srv.store.inbox[0]["seen"] is False  # the message is still unread, so the next run meets it again


def test_a_message_that_is_not_added_says_why_on_the_list(tmp_path):
    with StubMailServers() as srv:
        ctx = installed(tmp_path, srv)
        srv.store.deliver(mail("Dee <dee@mail.example.test>", "Application"))  # no role in the subject
        srv.store.deliver(mail("Eve <eve@mail.example.test>", "Application for Astronaut"))  # a role that does not exist
        srv.store.deliver(mail("Fay <fay@mail.example.test>", "Application for Customer Support Specialist", message_id="<f@x>"))
        srv.store.deliver(mail("Fay <fay@mail.example.test>", "Application for Customer Support Specialist", message_id="<f@x>"))  # the same message again
        out = run(ctx)
        assert out == {"added": 1, "duplicate": 1, "rejected": 2}
        rows = {(r.ref, r.status): r.detail for r in log_rows(ctx) if r.status != "added"}
        assert "does not name one of your roles" in rows[("dee@mail.example.test", "rejected")] and ("eve@mail.example.test", "rejected") in rows and ("fay@mail.example.test", "duplicate") in rows


def test_a_resume_nobody_can_read_still_brings_the_applicant_in_flagged_and_unscored(tmp_path):
    with StubMailServers() as srv:
        ctx = installed(tmp_path, srv)
        m = EmailMessage()
        m["From"], m["Subject"] = "Gus <gus@mail.example.test>", "Application for Customer Support Specialist"
        m.set_content("Hello")
        m.add_attachment(b"%PDF-1.4 this is not really a pdf at all", maintype="application", subtype="pdf", filename="cv.pdf")
        srv.store.deliver(m.as_bytes())
        out = run(ctx)
        assert out["added"] == 1
        with ctx.factory() as s:
            app = s.scalars(select(Application)).first()
            assert app.note.startswith("Resume missing")
            from slatehire import scoring_service
            assert app not in scoring_service.unscored(s)
            from slatehire.models import Resume
            assert s.scalars(select(Resume)).first().original_text == MISSING_RESUME
        notes = [r.detail for r in log_rows(ctx) if r.status == "added"]
        assert any("flagged" in n for n in notes)


def test_a_person_can_read_the_not_added_list_through_the_api(tmp_path):
    from fastapi.testclient import TestClient

    from hardening_helpers import sign_in
    from slatehire.api.app import create_app

    with StubMailServers() as srv:
        ctx = installed(tmp_path, srv)
        srv.store.deliver(mail("Dee <dee@mail.example.test>", "Application"))
        run(ctx)
        c = TestClient(create_app(ctx.settings, ctx), base_url="http://api.test")
        rows = c.get("/api/intake/log", headers=sign_in(c)).json()
        assert [r["ref"] for r in rows] == ["dee@mail.example.test"] and rows[0]["status"] == "rejected"
        assert c.get("/api/intake/log").status_code == 401


# ---- TLS ----

def self_signed(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = dt.datetime.now(dt.UTC)
    cert = x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(1).not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=1)).sign(key, hashes.SHA256())
    (tmp_path / "c.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (tmp_path / "k.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(tmp_path / "c.pem", tmp_path / "k.pem")
    return ctx


def test_the_mailbox_connection_refuses_a_certificate_nobody_vouches_for(tmp_path):
    tls = self_signed(tmp_path)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)

    def server(conn):
        try:
            tls.wrap_socket(conn, server_side=True)
        except (ssl.SSLError, OSError):
            pass

    threading.Thread(target=lambda: server(sock.accept()[0]), daemon=True).start()
    s = real_ctx(tmp_path, mailbox_adapter="imap", imap_host="127.0.0.1", imap_port=sock.getsockname()[1], imap_user="u", imap_password="p", imap_use_ssl=True).settings
    with pytest.raises(AdapterError, match="certificate"):
        ImapMailbox(s).fetch_new()
    assert ImapMailbox(s).healthcheck()[0] is False


def test_the_mailbox_connection_is_given_the_default_checking_context(tmp_path, monkeypatch):
    seen = {}

    def stub_imap(host, port, ssl_context=None, timeout=None, **kw):
        seen["ctx"] = ssl_context
        raise OSError("stop here")

    monkeypatch.setattr(mailbox_mod.imaplib, "IMAP4_SSL", stub_imap)
    s = real_ctx(tmp_path, mailbox_adapter="imap", imap_host="imap.provider.example.test", imap_user="u", imap_password="p").settings
    with pytest.raises(AdapterError):
        ImapMailbox(s).fetch_new()
    assert seen["ctx"].verify_mode == ssl.CERT_REQUIRED and seen["ctx"].check_hostname is True


def test_plain_text_imap_is_refused_for_any_host_but_this_computer(tmp_path):
    s = real_ctx(tmp_path, mailbox_adapter="imap", imap_host="imap.provider.example.test", imap_user="u", imap_password="p", imap_use_ssl=False).settings
    with pytest.raises(AdapterError, match="same computer"):
        ImapMailbox(s).fetch_new()
    assert any("IMAP_USE_SSL=false" in e for e in s.runtime_errors()) and any("IMAP_USE_SSL=false" in p for p in s.problems())
    from slatehire.config import is_loopback

    assert [is_loopback(h) for h in ("127.0.0.1", "localhost", "::1", "[::1]", "10.0.0.5", "mail.example.test", "")] == [True, True, True, True, False, False, False]
