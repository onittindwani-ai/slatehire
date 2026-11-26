"""Round 4, redaction: proxies for a protected attribute (a two digit graduation year, a club that names a group, family status, parental leave, a native language). Each test fails on the code before the fix."""

from __future__ import annotations

import time

import pytest
from sqlalchemy import select

from hardening_helpers import real_ctx
from slatehire import intake
from slatehire.ingest import Applicant
from slatehire.models import Resume, Role
from slatehire.redaction import PLACEHOLDER_RE, VERSION, redact

BODY = "Answered 40 customer emails a day on the support desk and cut errors by 12 percent."


@pytest.mark.parametrize("line,gone", [
    ("B.A., State University, Class of '08", "08"),
    ("Class of 08", "08"),
    ("Graduated with the class of ’09", "09"),
    ("Society of Women Engineers, treasurer", "Women"),
    ("National Society of Black Engineers, member", "Black"),
    ("Black Professionals Network, volunteer", "Black"),
    ("Hindu Students Council", "Hindu"),
    ("Muslim Students Association, president", "Muslim"),
    ("Alpha Kappa Alpha", "Kappa"),
    ("Phi Beta Kappa", "Kappa"),
    ("NAACP youth council", "NAACP"),
    ("Maternity leave, 2019", "Maternity"),
    ("Parental leave from March to September", "Parental leave"),
    ("Married with two children", "Married"),
    ("Single mother of three, returning to work", "Single mother"),
    ("Native Tamil speaker", "Tamil"),
    ("Mother tongue: Tamil", "Tamil"),
    ("Languages: Spanish (native), English (fluent)", "native"),
])
def test_a_proxy_for_a_protected_attribute_is_hidden_and_the_work_around_it_is_kept(line, gone):
    text = f"{BODY}\n{line}\n{BODY}"
    out = redact(text).redacted
    assert gone not in out, (line, out)
    assert out.count("Answered 40 customer emails a day on the support desk and cut errors by 12 percent.") == 2  # nothing about the work was lost
    assert PLACEHOLDER_RE.search(out)


@pytest.mark.parametrize("line", [
    "Ran beta testing of the new help centre and wrote the Pi Day quiz for the team.",
    "Built a health app for women's clinics and a tool for gay-friendly venue reviews.",
    "Single sign on for 40 apps, a parent child ticket link and a mother board repair guide.",
    "Led the Black Friday support rota and the Alpha release of the chat widget.",
    "Used native apps and native speakers of the product team.",
])
def test_ordinary_work_lines_with_those_words_are_not_redacted(line):
    assert redact(line).redacted == line


def test_the_owner_adds_clubs_in_the_settings_and_they_are_hidden_everywhere(tmp_path):
    ctx = real_ctx(tmp_path, redact_extra_terms="Chess Club, Lakeside Parish Choir")
    assert ctx.settings.redact_extra_term_list() == ("Chess Club", "Lakeside Parish Choir")
    with ctx.factory() as s:
        role = Role(key="support", title="Support")
        s.add(role)
        s.flush()
        text = f"Pat Quinn\n{BODY}\nChess Club captain, member of the Lakeside Parish Choir."
        app, status = intake.add_applicant(s, Applicant("Pat Quinn", "pat@mail.example.test", "", role.key, text, "", "paste"), role, "x", ctx.now(s), settings=ctx.settings)
        assert status == "added"
        res = s.scalars(select(Resume).where(Resume.application_id == app.id)).first()
        assert "Chess Club" not in res.redacted_text and "Parish Choir" not in res.redacted_text and res.redaction_version == VERSION


def test_the_new_patterns_cost_time_in_step_with_the_length_of_the_text():
    for hostile in ("Black " * 10000, "Black Network " * 5000, "Alpha " * 10000, "Mother of " * 6000, "married " * 8000, "Native " * 9000, "Class of " * 6000, "Society of Women " * 3500):
        started = time.perf_counter()
        redact(hostile[:60000])
        assert time.perf_counter() - started < 3.0, hostile[:12]


def test_the_redaction_version_moved_so_a_rubric_locked_now_names_the_new_rules():
    assert VERSION == "2"
