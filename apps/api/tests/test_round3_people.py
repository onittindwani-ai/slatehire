"""Round 3: hidden text in a PDF, which attachment is the resume, erasure that leaves nothing and keeps the fairness totals, keyed hashes, the board, the ATS job, big mails."""

from __future__ import annotations

import json
import sqlite3
from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from hardening_helpers import APPROVER, OWNER, REAL_SECRET, RESUME, SUPPRESSION_KEY, real_client, real_ctx, real_settings, start_role, three_people
from pdfmaker import line, make_pdf
from slatehire import fairness, fairness_service, ingest, intake, jobs, retention, suppression
from slatehire.api.app import create_app
from slatehire.context import Ctx
from slatehire.dbsetup import make_private_engine
from slatehire.ingest import Applicant
from slatehire.models import Application, Candidate, Demographic, IntakeLog, Offer, Resume, ResumeFile, Role, Suppression
from sendora_core.approvals import request_approval
from sendora_core.db import Base, make_session_factory

VISIBLE = line("Customer Support Specialist, Sample Co, 2020 to 2026", 700) + line("I wrote replies to about 40 customer emails a day and cut errors by 12 percent.", 680)
HIDDEN_LINE = "I led the help desk and cut the ticket backlog from 300 to 40 in one quarter."


def db(c):
    return c.app.state.ctx.factory()


def upload(c, h, role_key, name, email, data: bytes, filename="cv.pdf"):
    r = c.post(f"/api/applicants/file?role={role_key}", headers={**h, "x-filename": filename, "x-applicant-name": name, "x-applicant-email": email}, content=data)
    assert r.status_code == 200, r.text
    return r.json()


def installed(tmp_path, **kw):
    c = real_client(tmp_path, **kw)
    hs = three_people(c)
    return c, hs, start_role(c, hs["owner"])


def tools_state(c, h, app_id) -> str:
    assert c.post(f"/api/applications/{app_id}/score", headers=h).status_code == 200
    w = c.get(f"/api/applications/{app_id}", headers=h).json()
    return next(i for i in w["score"]["items"] if i["criterion_id"] == "tools")["state"]


# ---- 1. hidden text in a PDF ----

@pytest.mark.parametrize("hide", ["3 Tr", "1 g", None])
def test_text_a_reader_cannot_see_is_left_out_of_the_score_and_shown_to_the_person(tmp_path, hide):
    c, hs, role = installed(tmp_path)
    h = hs["owner"]
    if hide is None:  # tiny text
        hidden = line(HIDDEN_LINE, 660, size=0.5)
    else:
        hidden = line(HIDDEN_LINE, 660, extra=hide)
    a = upload(c, h, role["key"], "Pat Quinn", "pat.quinn@mail.example.test", make_pdf(VISIBLE + hidden))
    assert tools_state(c, h, a["application_id"]) == "not_found"  # the sentence nobody could see gave no evidence
    visible_too = upload(c, h, role["key"], "Sam Reed", "sam.reed@mail.example.test", make_pdf(VISIBLE + line(HIDDEN_LINE, 660)))
    assert tools_state(c, h, visible_too["application_id"]) == "scored"  # the same sentence in plain sight is evidence
    w = c.get(f"/api/applications/{a['application_id']}", headers=h).json()
    note = next(n for n in w["resume"]["notes"] if n["kind"] == "hidden_text")
    assert "Hidden text found" in note["detail"] and "private" not in note and HIDDEN_LINE not in json.dumps(w["resume"]["pieces"])  # blind: the hidden words are not shown either
    assert any(f["kind"] == "hidden_text" for f in w["score"]["flags"])
    shown = c.get(f"/api/applications/{a['application_id']}?reveal=true", headers=h)  # not blind: a stage past applied, or the reveal
    assert shown.status_code == 200


def test_white_text_on_a_dark_box_is_a_design_and_is_not_hidden_text():
    dark = "0.1 g 0 0 612 792 re f\n" + VISIBLE.replace("BT", "BT 1 g")
    got = ingest.read_resume(make_pdf(dark), "cv.pdf")
    assert got.hidden == [] and "Customer Support Specialist" in got.text


def test_text_outside_the_page_is_hidden_too():
    got = ingest.read_resume(make_pdf(VISIBLE + "BT /F1 11 Tf 900 600 Td (" + HIDDEN_LINE + ") Tj ET\n"), "cv.pdf")
    assert got.hidden and HIDDEN_LINE not in got.text and "off_page" in got.hidden_kinds


def test_the_original_pdf_is_kept_for_a_person_to_open_but_not_while_identity_is_hidden_and_goes_with_the_person(tmp_path):
    c, hs, role = installed(tmp_path)
    h = hs["owner"]
    pdf = make_pdf(VISIBLE + line(HIDDEN_LINE, 660, extra="3 Tr"))
    a = upload(c, h, role["key"], "Pat Quinn", "pat.quinn@mail.example.test", pdf)
    app_id = a["application_id"]
    assert c.get(f"/api/applications/{app_id}/original", headers=h).status_code == 403  # blind: the file holds the name
    assert c.post(f"/api/applications/{app_id}/score", headers=h).status_code == 200
    assert c.post(f"/api/applications/{app_id}/move", headers=h, json={"to": "shortlisted", "note": "Strong evidence on the main criteria."}).status_code == 200
    got = c.get(f"/api/applications/{app_id}/original", headers=h)
    assert got.status_code == 200 and got.content == pdf and "attachment" in got.headers["content-disposition"] and got.headers["content-type"] == "application/pdf"
    assert c.get(f"/api/applications/{app_id}/original", headers=hs["third"]).status_code == 200  # an approver may look too
    assert c.get(f"/api/applications/{app_id}", headers=h).json()["resume"]["has_original_file"] is True
    assert c.delete(f"/api/candidates/{app_id}", headers=h).status_code == 200
    assert c.get(f"/api/applications/{app_id}/original", headers=h).status_code == 404
    with db(c) as s:
        assert s.scalars(select(ResumeFile)).first() is None  # erased with the person


def test_a_pdf_over_the_keep_limit_is_read_but_not_kept(tmp_path):
    c, hs, role = installed(tmp_path, keep_original_max_bytes=1000)
    a = upload(c, hs["owner"], role["key"], "Pat Quinn", "pat.quinn@mail.example.test", make_pdf(VISIBLE + "% " + "x" * 3000 + "\n"))
    assert a["status"] == "added"
    with db(c) as s:
        assert s.scalars(select(ResumeFile)).first() is None


def test_a_page_with_a_huge_drawing_is_skipped_not_parsed(monkeypatch):
    monkeypatch.setattr(ingest, "MAX_PAGE_CONTENT_BYTES", 200)
    text, _hidden, _why, skipped = ingest._pdf_read(make_pdf(VISIBLE + "% " + "x" * 400 + "\n"))
    assert skipped == 1 and text.strip() == ""  # the page was not handed to the parser at all


# ---- 2. which attachment is the resume ----

def mail_with(*files: tuple[str, str], body: str = "Hello, I am applying.") -> bytes:
    m = EmailMessage()
    m["From"], m["Subject"] = "Pat Quinn <pat@mail.example.test>", "Application for Customer Support Specialist"
    m.set_content(body)
    for name, text in files:
        m.add_attachment(text.encode(), maintype="text", subtype="plain", filename=name)
    return m.as_bytes()


COVER = "Dear hiring team, I am writing to apply for the support role because I enjoy helping people and I would love to join your company. I look forward to hearing from you soon.\n" * 3
CV = "Pat Quinn\nSupport Specialist\nI wrote replies to about 40 customer emails a day on the help desk and cut the ticket backlog from 300 to 40 in one quarter.\n"
ROLES = {"support": "Customer Support Specialist"}


def test_a_cover_letter_that_comes_first_is_not_the_resume_and_the_choice_is_written_down():
    a = ingest.from_email(mail_with(("cover-letter.txt", COVER), ("Pat-CV.txt", CV)), ROLES)
    assert a.filename == "Pat-CV.txt" and "help desk" in a.resume_text
    note = next(n for n in a.extra["notes"] if n["kind"] == "attachment_choice")
    assert "2 readable files" in note["detail"] and "cover-letter.txt" in note["private"] and "cover-letter" not in note["detail"]  # no file name where a blind reader sees it


def test_with_no_name_to_go_by_the_largest_text_is_used_and_one_file_gives_no_note():
    big = CV * 3
    a = ingest.from_email(mail_with(("notes.txt", "x" * 50 + " short"), ("attachment.txt", big)), ROLES)
    assert a.filename == "attachment.txt"
    one = ingest.from_email(mail_with(("cv.txt", CV)), ROLES)
    assert not [n for n in one.extra.get("notes", []) if n["kind"] == "attachment_choice"]


def test_the_choice_is_shown_in_the_workspace_with_file_names_only_when_identity_is_shown(tmp_path):
    c, hs, role = installed(tmp_path)
    h = hs["owner"]
    ctx = c.app.state.ctx
    a = ingest.from_email(mail_with(("cover-letter.txt", COVER), ("cv.txt", CV)), {"support": "Support Specialist"} if False else {role["key"]: role["key"]}, keep_unreadable=True)
    with ctx.factory() as s:
        r = s.scalars(select(Role)).first()
        app, st = intake.add_applicant(s, Applicant("Pat Quinn", "pat@mail.example.test", "", r.key, a.resume_text, a.filename, "email", extra=a.extra), r, "mailbox", ctx.now(s), settings=ctx.settings)
        s.commit()
        app_id = app.id
    w = c.get(f"/api/applications/{app_id}", headers=h).json()
    note = next(n for n in w["resume"]["notes"] if n["kind"] == "attachment_choice")
    assert "private" not in note  # still blind


def test_an_unreadable_file_with_text_in_the_email_is_flagged_and_the_text_is_kept_for_a_person():
    m = EmailMessage()
    m["From"], m["Subject"] = "Pat Quinn <pat@mail.example.test>", "Application for Customer Support Specialist"
    m.set_content("Hello, my resume is attached as a Word file, and here is a short summary: I wrote replies to customer emails for four years on the help desk.")
    m.add_attachment(b"PK\x03\x04 not really", maintype="application", subtype="vnd.openxmlformats-officedocument.wordprocessingml.document", filename="resume.docx")
    a = ingest.from_email(m.as_bytes(), ROLES, keep_unreadable=True)
    assert a.extra.get("resume_missing") and a.resume_text == ingest.MISSING_RESUME
    note = next(n for n in a.extra["notes"] if n["kind"] == "body_not_used")
    assert "not scored as the resume" in note["detail"] and "help desk" in note["private"]


# ---- 4. the fairness report after deletions ----

def _person(s, role, n: int, group: str, selected: bool, declined: bool):
    cand = Candidate(code=f"C{n:04d}", full_name=f"Person {n}", email=f"p{n}@mail.example.test", source="paste")
    s.add(cand)
    s.flush()
    hist = [{"stage": "applied", "by": "x", "at": "2026-01-01", "note": "Applied."}] + ([{"stage": "shortlisted", "by": "x", "at": "2026-01-02", "note": ""}] if selected else [])
    app = Application(candidate_id=cand.id, role_id=role.id, stage="shortlisted" if selected else "declined" if declined else "applied", history=hist)
    s.add(app)
    s.flush()
    if group:
        s.add(Demographic(application_id=app.id, group_label=group))
    return app


def test_deleting_declined_people_does_not_turn_the_fairness_groups_into_too_few(tmp_path):
    ctx = real_ctx(tmp_path)
    with ctx.factory() as s:
        role = Role(key="support", title="Support")
        s.add(role)
        s.flush()
        n, declined = 0, []
        for group in ("Group A", "Group B"):
            for i in range(12):
                n += 1
                app = _person(s, role, n, group, selected=i < 6, declined=i >= 6)
                if i >= 6:
                    declined.append(app)
        s.commit()
        before, meta0 = fairness_service.counts(s, None)
        assert before["shortlisted"]["Group A"] == [12, 6] and before["shortlisted"]["Group B"] == [12, 6]
        for app in declined:
            retention.purge(s, app, "owner@x.test", ctx.now(s), "on request")
        s.commit()
        after, meta1 = fairness_service.counts(s, None)
        assert after["shortlisted"]["Group A"] == [12, 6] and after["shortlisted"]["Group B"] == [12, 6]  # the deleted people still count under their label
        assert fairness.UNDISCLOSED not in after["shortlisted"] and meta1["people"] == meta0["people"] == 24
        rep = fairness_service.run(s, "owner@x.test", None, 10).payload
        assert all(cell["status"] != "too_few" for cell in rep["stages"]["shortlisted"]["groups"].values())
        # nothing readable is kept: only role, step, group, month and counts
        from slatehire.models import FairnessAggregate

        rows = list(s.scalars(select(FairnessAggregate)))
        assert rows and all(len(r.month) == 7 for r in rows) and "Person" not in json.dumps([[r.group_label, r.step] for r in rows])


def test_a_person_is_folded_once(tmp_path):
    ctx = real_ctx(tmp_path)
    with ctx.factory() as s:
        role = Role(key="r", title="R")
        s.add(role)
        s.flush()
        app = _person(s, role, 1, "Group A", True, False)
        assert fairness_service.fold(s, app, ctx.now(s)) is True and fairness_service.fold(s, app, ctx.now(s)) is False


# ---- 5. erasure leaves no copy ----

def test_deleting_a_person_with_a_short_name_other_phone_layouts_and_a_second_application_leaves_nothing(tmp_path):
    ctx = real_ctx(tmp_path)
    export = tmp_path / "exports"
    export.mkdir()
    with ctx.factory() as s:
        r1, r2 = Role(key="support", title="Support"), Role(key="ops", title="Ops")
        s.add_all([r1, r2])
        s.flush()
        apps = []
        for i, role in enumerate((r1, r2), 1):
            cand = Candidate(code=f"C000{i}", full_name="Wu Li", email="Wu.Li@Mail.Example.Test", phone="(555) 010-0101", source="paste")
            s.add(cand)
            s.flush()
            app = Application(candidate_id=cand.id, role_id=role.id, stage="offer" if i == 1 else "applied", history=[{"stage": "applied", "by": "x", "at": "2026-01-01", "note": "Wu Li applied"}])
            s.add(app)
            s.flush()
            apps.append(app)
        ap = request_approval(s, "offer.approve", "Approve offer: Offer for Wu Li for candidate C0001", {"offer_id": 1}, "high", "pat@rivera.example.test")
        offer = Offer(application_id=apps[0].id, title="Offer for Wu Li", start_date="2027-01-01", terms="Call li on +1 555.010.0101 or 5550100101, wu li, WU LI, Li, WU.", body="To: Wu Li\nli@x\nPhone 555 010 0101\n", status="handed_off", approval_id=ap.id, handoff_ref="offer-1-c0001-offer-for-wu-li.txt")
        s.add(offer)
        s.flush()
        (export / offer.handoff_ref).write_text(offer.body)
        out = retention.purge_person(s, apps[0], "owner@x.test", ctx.now(s), "on request", export)
        s.commit()
        assert out["applications"] == 2 and out["also_removed"] == 1  # the other application of the same person goes too, and the answer says so
        text = json.dumps([[o.title, o.terms, o.body, o.handoff_ref] for o in s.scalars(select(Offer))] + [[a.summary, a.decision_note] for a in s.scalars(select(type(ap)))]).lower()
        for gone in ("wu", " li", "555", "0101", "wu li"):
            assert gone not in text.replace("(deleted)", ""), gone
        assert sorted(p.name for p in export.iterdir() if p.name.startswith("offer-")) == ["offer-1-c0001-erased.txt"]  # the file name carried the title
        assert "Wu" not in (export / "offer-1-c0001-erased.txt").read_text()
        assert s.scalars(select(Candidate).where(Candidate.purged_at.is_(None))).first() is None


def test_the_delete_answer_says_exactly_what_was_removed_and_a_second_erase_does_not_say_nothing_was_kept(tmp_path):
    c, hs, role = installed(tmp_path)
    h = hs["owner"]
    r1 = c.post("/api/applicants", headers=h, json={"name": "Dana Vale", "email": "dana.vale@mail.example.test", "role": role["key"], "resume_text": RESUME}).json()
    out = c.delete(f"/api/candidates/{r1['application_id']}", headers=h).json()
    assert out["applications_deleted"] == 1 and out["also_deleted"] == 0 and out["suppressed"] is True and out["removed"]["resumes"] == 1
    # the same person applies again later (the owner lifted the block), then asks to be deleted again
    assert c.post("/api/suppression/lift", headers=h, json={"email": "dana.vale@mail.example.test"}).json()["removed"] >= 1
    again = c.post("/api/applicants", headers=h, json={"name": "Dana Vale", "email": "dana.vale@mail.example.test", "role": role["key"], "resume_text": RESUME}).json()
    second = c.delete(f"/api/candidates/{again['application_id']}", headers=h).json()
    assert second["suppressed"] is True and "no address" not in second["note"]


# ---- 6. suppression keyed from the environment ----

def _session(tmp_path, key: str):
    ctx = real_ctx(tmp_path, suppression_key=key)
    s = ctx.factory()
    return ctx, s


def test_the_hash_depends_on_the_key_and_the_database_holds_no_salt(tmp_path):
    ctx, s = _session(tmp_path, SUPPRESSION_KEY)
    suppression.record(s, "ann@mail.example.test", "paste", None, ctx.now(s))
    s.commit()
    from slatehire.models import State

    assert s.get(State, suppression.SALT_KEY) is None  # nothing in the data lets a copy of it be tested
    assert suppression.is_suppressed(s, "Ann@Mail.Example.Test", "paste", None)
    s.info["suppression_key"] = "test-only-another-key-another-key-another"  # someone holding only a dump does not have the key
    assert not suppression.is_suppressed(s, "ann@mail.example.test", "paste", None)
    s.close()


@pytest.mark.parametrize("variant", ["ann+jobs@mail.example.test", " ANN@MAIL.EXAMPLE.TEST. ", "ann@mail.example.test,", "<ann@mail.example.test>", "ann＠mail.example.test", "ann+a+b@mail.example.test;"])
def test_the_same_address_in_other_spellings_is_still_the_same_person(tmp_path, variant):
    ctx, s = _session(tmp_path, SUPPRESSION_KEY)
    suppression.record(s, "ann@mail.example.test", "paste", None, ctx.now(s))
    assert suppression.is_suppressed(s, variant, "paste", None), variant
    s.close()


def test_lifting_by_address_also_lifts_the_reference_and_lifting_by_reference_works_alone(tmp_path):
    ctx, s = _session(tmp_path, SUPPRESSION_KEY)
    suppression.record(s, "ann@mail.example.test", "webhook", "ref-1", ctx.now(s))
    suppression.record(s, "", "webhook", "ref-2", ctx.now(s))
    assert suppression.count(s) == 3
    assert suppression.lift(s, "ann@mail.example.test", "owner@x.test") == 2  # the address and the reference of one erasure
    assert not suppression.is_suppressed(s, "", "webhook", "ref-1") and suppression.is_suppressed(s, "", "webhook", "ref-2")
    assert suppression.lift(s, "", "owner@x.test", "webhook", "ref-2") == 1 and suppression.count(s) == 0
    s.close()


def test_a_hash_made_before_the_key_existed_still_blocks_and_can_be_lifted(tmp_path):
    from slatehire.models import State
    import hashlib
    import hmac

    ctx, s = _session(tmp_path, SUPPRESSION_KEY)
    s.add(State(key=suppression.SALT_KEY, value="oldsalt"))
    digest = hmac.new(b"oldsalt", b"email:old@mail.example.test", hashlib.sha256).hexdigest()
    s.add(Suppression(digest=digest, kind="email", scheme="salt", created_at=ctx.now(s)))
    s.flush()
    assert suppression.is_suppressed(s, "OLD@mail.example.test", "paste", None)
    assert suppression.lift(s, "old@mail.example.test", "owner@x.test") == 1 and not suppression.is_suppressed(s, "old@mail.example.test", "paste", None)
    s.close()


def test_a_real_install_needs_a_suppression_key(tmp_path):
    from sendora_core.settings import ConfigError

    with pytest.raises(ConfigError, match="SUPPRESSION_KEY"):
        real_settings(tmp_path, suppression_key="").check_runtime()
    real_settings(tmp_path).check_runtime()
    bare = real_settings(tmp_path, suppression_key="", owner_password_hash=None)  # nobody can sign in yet: it starts, and the settings page and the doctor say what is missing
    bare.check_runtime()
    assert any("SUPPRESSION_KEY" in p for p in bare.problems())


def test_the_erased_list_is_written_only_after_the_deletion_is_saved(tmp_path):
    ctx = real_ctx(tmp_path)
    list_file = tmp_path / "exports" / suppression.ERASED_LIST
    with ctx.factory() as s:
        suppression.record(s, "ann@mail.example.test", "paste", None, ctx.now(s))
        s.rollback()
    assert not list_file.exists()
    with ctx.factory() as s:
        suppression.record(s, "ann@mail.example.test", "paste", "ref-9", ctx.now(s))
        s.commit()
    lines = list_file.read_text().splitlines()
    assert len(lines) == 2 and all(len(x.split()[0]) == 64 and "ann" not in x for x in lines)
    assert (list_file.stat().st_mode & 0o077) == 0


# ---- 7. after a restore ----

def test_a_restore_followed_by_the_erased_list_deletes_again_whoever_asked_in_between(tmp_path):
    from slatehire import reapply

    ctx = real_ctx(tmp_path)
    with ctx.factory() as s:
        role = Role(key="support", title="Support")
        s.add(role)
        s.commit()
        for name, mail in (("Ann Vale", "ann@mail.example.test"), ("Bo Reed", "bo@mail.example.test")):
            intake.add_applicant(s, Applicant(name, mail, "", "support", RESUME, "", "paste"), role, "x", ctx.now(s), settings=ctx.settings)
        s.commit()
    snapshot = tmp_path / "old.sqlite3"  # the backup, made while both were still here
    src = sqlite3.connect(tmp_path / "r.sqlite3")
    dst = sqlite3.connect(snapshot)
    src.backup(dst)
    src.close(), dst.close()
    with ctx.factory() as s:  # then Ann asks to be deleted
        ann = s.scalars(select(Application).join(Candidate, Candidate.id == Application.candidate_id).where(Candidate.full_name == "Ann Vale")).first()
        retention.purge_person(s, ann, OWNER, ctx.now(s), "on request", ctx.settings.export_dir)
        s.commit()
    listed = (tmp_path / "exports" / suppression.ERASED_LIST).read_text()
    restored = Ctx(real_settings(tmp_path, database_url=f"sqlite:///{snapshot}"), make_session_factory(make_private_engine(f"sqlite:///{snapshot}")))
    with restored.factory() as s:
        assert len(list(s.scalars(select(Candidate).where(Candidate.purged_at.is_(None))))) == 2  # the restore brought Ann back
        out = reapply.apply(s, reapply.read_list(listed), restored.now(s), restored.settings.export_dir)
        s.commit()
        assert out["people_deleted"] == 1 and [c.full_name for c in s.scalars(select(Candidate).where(Candidate.purged_at.is_(None)))] == ["Bo Reed"]
        assert suppression.is_suppressed(s, "ann@mail.example.test", "paste", None)  # and she cannot be added again
    assert reapply.read_list("garbage\n" + listed + "\nzz email g") == reapply.read_list(listed)


def test_the_backup_script_mirrors_its_rotation_to_the_copy_and_keeps_the_erased_list(tmp_path):
    import os
    import stat
    import subprocess
    import time
    from pathlib import Path

    root = tmp_path / "repo"
    (root / "deploy" / "hetzner").mkdir(parents=True)
    src = Path(__file__).resolve().parents[3] / "deploy" / "hetzner" / "backup.sh"
    script = root / "deploy" / "hetzner" / "backup.sh"
    script.write_text(src.read_text())
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    (bin_dir / "docker").write_text('#!/bin/sh\ncase "$*" in\n*pg_dump*) echo DUMP;;\n*"tar -C /data"*) echo TAR;;\n*erased-hashes*) printf "%s\\n" "aa email g1";;\nesac\n')
    (bin_dir / "rsync").write_text(f'#!/bin/sh\necho "rsync $*" >> "{log}"\n')
    for f in bin_dir.iterdir():
        f.chmod(f.stat().st_mode | stat.S_IEXEC)
    out = tmp_path / "backups"
    out.mkdir()
    for i in range(20):  # twenty older dumps
        p = out / f"slatehire-2026010{i % 10}-00{i:02d}.dump"
        p.write_text("old")
        os.utime(p, (time.time() - 10_000 + i, time.time() - 10_000 + i))
    (out / "erased-hashes-all.txt").write_text("bb ref g0\n")
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "BACKUP_DIR": str(out), "BACKUP_COPY_TO": "user@host:/backups/slatehire/"}
    done = subprocess.run(["sh", str(script)], capture_output=True, text=True, env=env, timeout=60)
    assert done.returncode == 0, done.stderr
    assert len(list(out.glob("slatehire-*.dump"))) == 14
    assert "--delete" in log.read_text()  # an old copy that rotated out here goes from the other machine too
    assert sorted((out / "erased-hashes-all.txt").read_text().split("\n")[:-1]) == ["aa email g1", "bb ref g0"]  # the list only grows


def test_the_restore_script_restores_then_reapplies_the_list(tmp_path):
    import os
    import stat
    import subprocess
    from pathlib import Path

    root = tmp_path / "repo"
    (root / "deploy" / "hetzner").mkdir(parents=True)
    src = Path(__file__).resolve().parents[3] / "deploy" / "hetzner" / "restore.sh"
    (root / "deploy" / "hetzner" / "restore.sh").write_text(src.read_text())
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    (bin_dir / "docker").write_text(f'#!/bin/sh\necho "docker $*" >> "{log}"\ncase "$*" in *reapply*) cat >> "{log}";; esac\n')
    (bin_dir / "docker").chmod(0o755 | stat.S_IEXEC)
    dump = tmp_path / "slatehire-1.dump"
    dump.write_text("DUMP")
    (tmp_path / "erased-hashes-all.txt").write_text("aa email g1\n")
    done = subprocess.run(["sh", str(root / "deploy" / "hetzner" / "restore.sh"), str(dump)], capture_output=True, text=True, env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}, timeout=60)
    assert done.returncode == 0, done.stderr
    calls = log.read_text()
    assert calls.index("pg_restore") < calls.index("reapply") and "aa email g1" in calls
    bad = subprocess.run(["sh", str(root / "deploy" / "hetzner" / "restore.sh"), str(tmp_path / "missing.dump")], capture_output=True, text=True, timeout=60)
    assert bad.returncode == 1


# ---- 9. big mail ----

def test_a_message_over_the_size_limit_is_never_downloaded_and_is_listed_once(tmp_path):
    from mock.mail_servers import StubMailServers
    from test_hardening_mail import GOOD, installed as mail_installed, mail, run

    with StubMailServers() as srv:
        ctx = mail_installed(tmp_path, srv)
        ctx.settings.imap_max_message_bytes = 100_000
        srv.store.deliver(mail("Big Sender <big@mail.example.test>", "Application for Customer Support Specialist", GOOD + "x" * 150_000, message_id="<big@x>"))
        srv.store.deliver(mail("Ann <ann@mail.example.test>", "Application for Customer Support Specialist", GOOD, message_id="<ann@x>"))
        out = run(ctx)
        assert out["added"] == 1 and out["rejected"] == 1
        with ctx.factory() as s:
            row = s.scalars(select(IntakeLog).where(IntakeLog.status == "rejected")).first()
            assert "IMAP_MAX_MESSAGE_BYTES" in row.detail and "big@mail.example.test" in row.ref
        assert all(m["seen"] for m in srv.store.inbox)  # marked read, so it is not listed again every five minutes
        assert run(ctx) == {"added": 0, "duplicate": 0, "rejected": 0}


def test_one_mailbox_run_holds_only_so_many_bytes_and_the_rest_waits(tmp_path):
    from mock.mail_servers import StubMailServers
    from test_hardening_mail import GOOD, installed as mail_installed, mail, run

    with StubMailServers() as srv:
        ctx = mail_installed(tmp_path, srv)
        ctx.settings.imap_max_message_bytes = 100_000
        ctx.settings.imap_max_run_bytes = 100_000
        for i in range(3):
            srv.store.deliver(mail(f"P{i} <p{i}@mail.example.test>", "Application for Customer Support Specialist", GOOD + "y" * 40_000, message_id=f"<m{i}@x>"))
        assert run(ctx)["added"] == 2  # two fit in the run, the third stays unread
        assert run(ctx)["added"] == 1


# ---- 11. the ATS job ----

def ats_client(tmp_path, job_id: str | None):
    from slatehire.adapters.ats import Greenhouse
    from mock.vendor_mocks import GreenhouseMock

    mock = GreenhouseMock()
    st = real_settings(tmp_path, ats_adapter="greenhouse", greenhouse_token=mock.token, allow_http_local_targets=True)
    engine = make_private_engine(st.database_url)
    Base.metadata.create_all(engine)
    ctx = Ctx(st, make_session_factory(engine), adapters={"ats": Greenhouse(st, TestClient(mock.app, base_url="http://testserver"))})
    c = TestClient(create_app(st, ctx), base_url="http://api.test")
    hs = three_people(c)
    role = start_role(c, hs["owner"])
    if job_id is not None:
        assert c.put(f"/api/roles/{role['id']}", headers=hs["owner"], json={"ats_job_id": job_id}).status_code == 200
    return c, hs, role


def test_an_ats_pull_without_a_job_id_is_refused(tmp_path):
    c, hs, role = ats_client(tmp_path, None)
    r = c.post(f"/api/intake/ats?role={role['key']}", headers=hs["owner"])
    assert r.status_code == 400 and "job id" in r.json()["error"]["message"]
    with db(c) as s:
        assert s.scalars(select(Candidate)).first() is None


def test_an_ats_pull_brings_in_only_the_people_of_that_job(tmp_path):
    c, hs, role = ats_client(tmp_path, "88")
    out = c.post(f"/api/intake/ats?role={role['key']}", headers=hs["owner"]).json()
    assert out["added"] == 2  # job 88 has two candidates in the mock ATS, the other three belong to job 77
    assert [r["ats_job_id"] for r in c.get("/api/roles", headers=hs["owner"]).json()] == ["88"]
    c2, hs2, role2 = ats_client(tmp_path / "second", "77") if (tmp_path / "second").mkdir() is None else (None, None, None)
    assert c2.post(f"/api/intake/ats?role={role2['key']}", headers=hs2["owner"]).json()["added"] == 3


def test_the_ats_job_id_is_a_plain_token(tmp_path):
    c, hs, role = ats_client(tmp_path, None)
    assert c.put(f"/api/roles/{role['id']}", headers=hs["owner"], json={"ats_job_id": "bad id; drop"}).status_code == 422


# ---- 12 and the cheap Lows: the board and the lists ----

def test_people_who_need_a_person_come_first_on_the_board_and_are_never_cut_off(tmp_path):
    from test_round2_people import SPANISH

    c, hs, role = installed(tmp_path)
    h = hs["owner"]
    ids = []
    for i in range(43):
        a = c.post("/api/applicants", headers=h, json={"name": f"Pat Number{i}", "email": f"pat{i}@mail.example.test", "role": role["key"], "resume_text": RESUME}).json()
        assert c.post(f"/api/applications/{a['application_id']}/score", headers=h).status_code == 200
        ids.append(a["application_id"])
    lang = c.post("/api/applicants", headers=h, json={"name": "Lena Ruiz", "email": "lena@mail.example.test", "role": role["key"], "resume_text": SPANISH}).json()["application_id"]
    ctx = c.app.state.ctx
    with ctx.factory() as s:
        r = s.scalars(select(Role)).first()
        app, _st = intake.add_applicant(s, Applicant("Mo Chen", "mo@mail.example.test", "", r.key, "", "", "email", extra={"resume_missing": "no file"}), r, "mailbox", ctx.now(s), settings=ctx.settings)
        s.commit()
        missing = app.id
    board = c.get("/api/pipeline?per_stage=40", headers=h).json()["applied"]
    assert board["count"] == 45 and len(board["cards"]) == 42  # 40 by score and the two who need a person
    assert {board["cards"][0]["id"], board["cards"][1]["id"]} == {lang, missing} and all(card["attention"] for card in board["cards"][:2])


def test_the_candidate_list_does_not_ask_the_database_once_per_person(tmp_path):
    c, hs, role = installed(tmp_path)
    h = hs["owner"]

    def statements() -> int:
        n = []
        engine = c.app.state.ctx.factory.kw["bind"]
        tick = lambda *_a, **_k: n.append(1)  # noqa: E731
        event.listen(engine, "before_cursor_execute", tick)
        try:
            assert c.get("/api/applications", headers=h).status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", tick)
        return len(n)

    for i in range(3):
        c.post("/api/applicants", headers=h, json={"name": f"Pat Few{i}", "email": f"few{i}@mail.example.test", "role": role["key"], "resume_text": RESUME})
    small = statements()
    for i in range(12):
        c.post("/api/applicants", headers=h, json={"name": f"Pat More{i}", "email": f"more{i}@mail.example.test", "role": role["key"], "resume_text": RESUME})
    assert statements() == small


def test_the_quote_check_page_is_served_from_the_kept_result(tmp_path, monkeypatch):
    from slatehire import scoring_service

    c, hs, role = installed(tmp_path)
    h = hs["owner"]
    a = c.post("/api/applicants", headers=h, json={"name": "Pat Quinn", "email": "pat@mail.example.test", "role": role["key"], "resume_text": RESUME}).json()
    c.post(f"/api/applications/{a['application_id']}/score", headers=h)
    calls = []
    real = scoring_service.quote_check
    monkeypatch.setattr(scoring_service, "quote_check", lambda s: calls.append(1) or real(s))
    for _ in range(3):
        assert c.get("/api/evals", headers=h).json()["quote_check"]["invalid"] == 0
    assert len(calls) == 1


def test_the_access_log_does_not_carry_the_query_string(tmp_path):
    import logging

    from slatehire.api.app import QueryStringFilter

    rec = logging.LogRecord("uvicorn.access", logging.INFO, "x", 1, '%s - "%s %s HTTP/%s" %d', ("127.0.0.1:1", "POST", "/api/applicants/file?role=support&name=Pat%20Quinn&email=pat@x.test", "1.1", 200), None)
    assert QueryStringFilter().filter(rec) and "Pat" not in rec.getMessage() and "/api/applicants/file" in rec.getMessage()


def test_the_api_answers_carry_a_content_security_policy(tmp_path):
    c, hs, role = installed(tmp_path)
    r = c.get("/health")
    assert "default-src 'none'" in r.headers.get("content-security-policy", "")
