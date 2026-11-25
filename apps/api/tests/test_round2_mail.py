"""Round 2 audit: the mailbox job touches only application mail, and says so exactly."""

from __future__ import annotations

from email.message import EmailMessage

from sqlalchemy import select

from slatehire.models import Application, Candidate, IntakeLog, Resume
from mock.mail_servers import FakeMailServers
from test_hardening_mail import installed, log_rows, mail, run

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 12


def test_other_peoples_mail_in_a_shared_inbox_is_never_read_stored_or_marked_read(tmp_path):
    with FakeMailServers() as srv:
        ctx = installed(tmp_path, srv)
        srv.store.deliver(mail("Colleague <colleague@rivera.example.test>", "Lunch on Friday?"))
        srv.store.deliver(mail("Bank <bank@mail.example.test>", "Your statement is ready"))
        srv.store.deliver(mail("Ann <ann@mail.example.test>", "Application for Customer Support Specialist", message_id="<a1@x>"))
        out = run(ctx)
        assert out == {"added": 1, "duplicate": 0, "rejected": 0}
        seen = {m["uid"]: m["seen"] for m in srv.store.inbox}
        assert seen == {1: False, 2: False, 3: True}  # only the application mail was read and marked
        assert [r.ref for r in log_rows(ctx)] == ["ann@mail.example.test"]  # nothing about the lunch or the bank anywhere


def test_the_subject_search_is_done_by_the_server_not_after_the_fetch(tmp_path):
    from slatehire.adapters.mailbox import ImapMailbox

    with FakeMailServers() as srv:
        ctx = installed(tmp_path, srv)
        srv.store.deliver(mail("Colleague <colleague@rivera.example.test>", "Private note"))
        srv.store.deliver(mail("Ann <ann@mail.example.test>", "application for customer support specialist"))  # the case of the subject does not matter
        got = ImapMailbox(ctx.settings).fetch_new()
        assert [u for u, _ in got] == ["2"]


def test_an_application_mail_with_a_picture_first_is_added_with_the_real_resume(tmp_path):
    with FakeMailServers() as srv:
        ctx = installed(tmp_path, srv)
        m = EmailMessage()
        m["From"], m["Subject"] = "Pat Quinn <pat@mail.example.test>", "Application for Customer Support Specialist"
        m.set_content("Hello")
        m.add_attachment(PNG, maintype="image", subtype="png", filename="image001.png")
        m.add_attachment(b"I wrote replies to customer emails every day and trained three colleagues on the help desk tools at my last job.\n", maintype="text", subtype="plain", filename="cv.txt")
        srv.store.deliver(m.as_bytes())
        assert run(ctx)["added"] == 1
        with ctx.factory() as s:
            res = s.scalars(select(Resume)).first()
            assert "help desk" in res.original_text and "PNG" not in res.original_text
            assert not s.scalars(select(Application)).first().note.startswith("Resume missing")


def test_a_subject_that_fits_two_roles_goes_to_the_list_and_nobody_is_added(tmp_path):
    from slatehire import rubric_service

    with FakeMailServers() as srv:
        ctx = installed(tmp_path, srv)
        with ctx.factory() as s:
            rubric_service.create_role(s, "sam@rivera.example.test", "Customer Support Lead", "Support", "Leads support.", key="lead")
            s.commit()
        srv.store.deliver(mail("Ann <ann@mail.example.test>", "Application for Customer Support"))
        out = run(ctx)
        assert out["added"] == 0 and out["rejected"] == 1
        row = [r for r in log_rows(ctx) if r.status == "rejected"][0]
        assert "more than one role" in row.detail and "Customer Support Lead" in row.detail
        with ctx.factory() as s:
            assert s.scalars(select(Candidate)).first() is None


def test_an_application_mail_that_is_not_added_is_on_the_list_and_not_fetched_again(tmp_path):
    with FakeMailServers() as srv:
        ctx = installed(tmp_path, srv)
        srv.store.deliver(mail("Eve <eve@mail.example.test>", "Application for Astronaut"))
        assert run(ctx)["rejected"] == 1
        assert run(ctx) == {"added": 0, "duplicate": 0, "rejected": 0}
        assert len([r for r in log_rows(ctx) if r.status == "rejected"]) == 1  # one line, however many times the job runs
        with ctx.factory() as s:
            assert s.scalar(select(IntakeLog.id).limit(1)) is not None
