"""Round 4, the PDF reader: text a person cannot see, and a scan that has a text layer. Each test fails on the code before the fix."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from pdfmaker import build_pdf, line, make_pdf
from slatehire import ingest, intake
from slatehire.models import ResumeFile, Role
from test_round3_people import HIDDEN_LINE, VISIBLE, installed, tools_state, upload

HIDDEN = HIDDEN_LINE


def white(text: str = HIDDEN, y: int = 640, size: int = 11, extra: str = "") -> str:
    return f"BT 1 g {extra} /F1 {size} Tf 72 {y} Td ({text}) Tj ET\n"


def read(content: str, **kw):
    return ingest.read_resume(build_pdf(content, **kw), "cv.pdf")


def assert_left_out(got, kind: str | None = None) -> None:
    assert got.hidden and HIDDEN not in got.text, (got.hidden, got.text)
    assert "Customer Support Specialist" in got.text  # what a person can read is still read
    if kind:
        assert kind in got.hidden_kinds, got.hidden_kinds


# ---- one dark rectangle somewhere else on the page does not make white text a design ----

def test_white_text_and_one_small_dark_rectangle_far_from_it_is_still_hidden_text():
    assert_left_out(read(VISIBLE + "0 g 0 0 2 2 re f\n" + white()), "white")


def test_white_text_and_a_dark_logo_on_the_page_is_still_hidden_text():
    got = read(VISIBLE + "q 40 0 0 40 500 700 cm /Im1 Do Q\n" + white(), images={"Im1": 0})
    assert_left_out(got, "white")


def test_white_text_far_from_a_dark_header_band_is_still_hidden_text():
    band = "q 0.1 g 0 740 612 52 re f\nBT 1 g /F1 20 Tf 72 760 Td (Pat Quinn, Customer Support) Tj ET Q\n"
    got = read(band + VISIBLE + white(y=300))
    assert got.hidden == [HIDDEN] and "Pat Quinn, Customer Support" in got.text and HIDDEN not in got.text  # the band's own white text is a design, the other line is not


def test_white_text_on_a_dark_header_band_that_covers_it_is_a_design():
    got = read("q 0.1 g 0 700 612 92 re f\nBT 1 g /F1 20 Tf 72 740 Td (Pat Quinn, Customer Support Specialist) Tj ET Q\n" + VISIBLE.replace("700", "650").replace("680", "630"))
    assert got.hidden == [] and "Pat Quinn" in got.text


def test_white_text_on_a_dark_box_inside_a_form_is_a_design_and_outside_it_is_not():
    form = "0.1 g 0 700 612 92 re f\nBT 1 g /F1 20 Tf 72 740 Td (Pat Quinn, Customer Support Specialist) Tj ET\n"
    got = read("/Fm1 Do\n" + VISIBLE.replace("700", "650").replace("680", "630") + white(y=300), forms={"Fm1": form})
    assert got.hidden == [HIDDEN] and "Pat Quinn" in got.text


def test_dark_text_on_a_dark_box_cannot_be_read_either():
    got = read(VISIBLE + "0 g 50 600 500 60 re f\nBT 0 g /F1 11 Tf 72 630 Td (" + HIDDEN + ") Tj ET\n")
    assert_left_out(got, "white")


# ---- the other ways to leave text out of sight ----

def test_white_text_inside_a_form_is_hidden_text():
    form = f"BT /F1 11 Tf 1 g 72 640 Td ({HIDDEN}) Tj ET\n"
    assert_left_out(read(VISIBLE + "/Fm1 Do\n", forms={"Fm1": form}), "white")


def test_text_in_a_form_that_inherits_white_from_the_page_is_hidden_text():
    form = f"BT /F1 11 Tf 72 640 Td ({HIDDEN}) Tj ET\n"
    assert_left_out(read(VISIBLE + "1 g /Fm1 Do\n", forms={"Fm1": form}), "white")


@pytest.mark.parametrize("grey", ["0.90", "0.95", "0.86"])
def test_very_pale_grey_text_is_hidden_text(grey):
    assert_left_out(read(VISIBLE + f"BT {grey} g /F1 11 Tf 72 640 Td ({HIDDEN}) Tj ET\n"), "white")


@pytest.mark.parametrize("grey", ["0.5", "0.6", "0.8"])
def test_grey_text_that_can_be_read_is_not_hidden_text(grey):
    got = read(VISIBLE + f"BT {grey} g /F1 11 Tf 72 640 Td ({HIDDEN}) Tj ET\n")
    assert got.hidden == [] and HIDDEN in got.text


def test_text_with_no_width_is_hidden_text():
    assert_left_out(read(VISIBLE + f"BT /F1 11 Tf 0 Tz 72 640 Td ({HIDDEN}) Tj ET\n"), "tiny")


def test_text_lifted_far_off_the_page_by_the_rise_is_hidden_text():
    assert_left_out(read(VISIBLE + f"BT /F1 11 Tf 5000 Ts 72 640 Td ({HIDDEN}) Tj ET\n"), "off_page")


def test_white_outline_text_is_hidden_text_and_a_black_outline_is_not():
    assert_left_out(read(VISIBLE + f"BT 1 G 1 Tr /F1 11 Tf 72 640 Td ({HIDDEN}) Tj ET\n"), "white")
    got = read(VISIBLE + f"BT 0 G 1 Tr /F1 11 Tf 72 640 Td ({HIDDEN}) Tj ET\n")
    assert got.hidden == [] and HIDDEN in got.text


def test_text_outside_the_crop_box_is_hidden_text():
    inside = line("Customer Support Specialist, Sample Co, 2020 to 2026", 280) + line("I wrote replies to about 40 customer emails a day and cut errors by 12 percent.", 260)
    got = read(inside + f"BT /F1 11 Tf 72 640 Td ({HIDDEN}) Tj ET\n", cropbox=(0, 0, 300, 300))
    assert_left_out(got, "off_page")


def test_text_in_a_layer_that_is_switched_off_is_hidden_text_and_in_a_layer_that_is_on_is_not():
    body = VISIBLE + f"/OC /L1 BDC BT /F1 11 Tf 72 640 Td ({HIDDEN}) Tj ET EMC\n"
    assert_left_out(read(body, layers={"L1": False}), "layer_off")
    on = read(body, layers={"L1": True})
    assert on.hidden == [] and HIDDEN in on.text


def test_a_form_that_belongs_to_a_layer_that_is_switched_off_is_hidden_text():
    form = f"BT /F1 11 Tf 72 640 Td ({HIDDEN}) Tj ET\n"
    assert_left_out(read(VISIBLE + "/Fm1 Do\n", forms={"Fm1": form}, layers={"L1": False}, form_layers={"Fm1": "L1"}), "layer_off")
    on = read(VISIBLE + "/Fm1 Do\n", forms={"Fm1": form}, layers={"L1": True}, form_layers={"Fm1": "L1"})
    assert on.hidden == [] and HIDDEN in on.text


def test_a_form_that_is_moved_by_its_own_matrix_is_followed_to_where_it_lands():
    form = f"BT /F1 11 Tf 0 g 72 100 Td ({HIDDEN}) Tj ET\n"  # drawn at y 100 in the form, lifted by 540 to y 640 on the page
    got = read(VISIBLE + "/Fm1 Do\n", forms={"Fm1": form}, form_matrix=[1, 0, 0, 1, 0, 540])
    assert got.hidden == [] and HIDDEN in got.text
    off = read(VISIBLE + "/Fm1 Do\n", forms={"Fm1": form}, form_matrix=[1, 0, 0, 1, 0, 5000])  # and a form moved off the page takes its text with it
    assert_left_out(off, "off_page")


def test_the_colour_changed_after_the_text_was_shown_does_not_hide_it_from_the_check():
    assert_left_out(read(VISIBLE + f"BT 1 g /F1 11 Tf 72 640 Td ({HIDDEN}) Tj 0 g ET\n"), "white")


def test_text_clipped_away_is_hidden_text():
    assert_left_out(read(VISIBLE + f"q 0 0 10 10 re W n BT 0 g /F1 11 Tf 72 640 Td ({HIDDEN}) Tj ET Q\n"), "off_page")


def test_hidden_text_that_repeats_a_visible_line_is_removed_where_it_stands_not_where_the_same_words_first_appear():
    first = "Customer Support Specialist, Sample Co, 2020 to 2026"
    body = line(first, 700) + line("I wrote replies to about 40 customer emails a day and cut errors by 12 percent.", 680) + white(first, 660)
    got = read(body)
    assert got.hidden == [first]
    assert got.text.splitlines()[0] == first and got.text.count(first) == 1 and got.text.splitlines()[-1].startswith("I wrote replies")


def test_ordinary_resumes_and_the_old_designs_are_still_read_whole():
    plain = ingest.read_resume(make_pdf(VISIBLE), "cv.pdf")
    assert plain.hidden == [] and "Customer Support Specialist" in plain.text and "cut errors by 12 percent" in plain.text
    dark = "0.1 g 0 0 612 792 re f\n" + VISIBLE.replace("BT", "BT 1 g")
    assert ingest.read_resume(make_pdf(dark), "cv.pdf").hidden == []


# ---- hidden text reaches the score as it did before ----

def test_a_resume_with_white_text_and_a_dark_rectangle_scores_nothing_for_the_hidden_line(tmp_path):
    c, hs, role = installed(tmp_path)
    h = hs["owner"]
    tricked = upload(c, h, role["key"], "Pat Quinn", "pat.quinn@mail.example.test", build_pdf(VISIBLE + "0 g 0 0 2 2 re f\n" + white(y=660)))
    assert tools_state(c, h, tricked["application_id"]) == "not_found"
    note = next(n for n in c.get(f"/api/applications/{tricked['application_id']}", headers=h).json()["resume"]["notes"] if n["kind"] == "hidden_text")
    assert "Hidden text found" in note["detail"]


# ---- a scan that has a text layer ----

SCAN_TEXT = "Customer Support Specialist, Sample Co, 2020 to 2026. I wrote replies to about 40 customer emails a day and cut errors by 12 percent."
SCAN_PAGE = "q 612 0 0 792 0 0 cm /Im1 Do Q\n" + f"BT 3 Tr /F1 11 Tf 72 700 Td ({SCAN_TEXT}) Tj ET\n"


def test_a_searchable_scan_is_read_and_says_where_its_words_came_from():
    pdf = build_pdf(SCAN_PAGE, images={"Im1": 255})
    got = ingest.read_resume(pdf, "scan.pdf")
    assert got.hidden == [] and "cut errors by 12 percent" in got.text and got.original == pdf
    kinds = {n["kind"]: n for n in got.notes()}
    assert "ocr_layer" in kinds and "scan" in kinds["ocr_layer"]["detail"].lower() and "hidden_text" not in kinds


def test_a_pdf_with_a_typed_page_and_a_scanned_page_reads_both_without_an_accusation():
    typed = build_pdf(VISIBLE, extra_pages=[SCAN_PAGE], images={"Im1": 255})
    got = ingest.read_resume(typed, "mixed.pdf")
    assert got.hidden == [] and "Customer Support Specialist, Sample Co, 2020 to 2026\nI wrote" in got.text and "cut errors by 12 percent." in got.text
    assert [n["kind"] for n in got.notes()] == ["ocr_layer"]


def test_a_page_with_typed_text_and_an_invisible_layer_is_still_hidden_text():
    got = read("q 612 0 0 792 0 0 cm /Im1 Do Q\n" + VISIBLE + f"BT 3 Tr /F1 11 Tf 72 640 Td ({HIDDEN}) Tj ET\n", images={"Im1": 255})
    assert_left_out(got, "invisible")


def test_invisible_text_with_no_picture_behind_it_is_still_hidden_text():
    assert_left_out(read(VISIBLE + f"BT 3 Tr /F1 11 Tf 72 640 Td ({HIDDEN}) Tj ET\n"), "invisible")


def test_a_searchable_scan_enters_the_process_flagged_and_its_original_is_kept(tmp_path):
    c, hs, role = installed(tmp_path)
    h = hs["owner"]
    pdf = build_pdf(SCAN_PAGE, images={"Im1": 255})
    a = upload(c, h, role["key"], "Pat Quinn", "pat.quinn@mail.example.test", pdf, "scan.pdf")
    w = c.get(f"/api/applications/{a['application_id']}", headers=h).json()
    assert w["attention"] is None and w["resume"]["has_original_file"] is True
    assert any(n["kind"] == "ocr_layer" for n in w["resume"]["notes"])
    assert c.post(f"/api/applications/{a['application_id']}/score", headers=h).status_code == 200
    scored = c.get(f"/api/applications/{a['application_id']}", headers=h).json()
    assert any(f["kind"] == "ocr_layer" for f in scored["score"]["flags"])  # nobody reads the score without being told the words came from a scan's text layer


def test_a_picture_only_pdf_enters_flagged_as_missing_and_the_file_is_kept_for_a_person(tmp_path):
    c, hs, role = installed(tmp_path)
    pdf = build_pdf("q 612 0 0 792 0 0 cm /Im1 Do Q\n", images={"Im1": 255})
    from email.message import EmailMessage

    m = EmailMessage()
    m["From"], m["Subject"] = "Pat Quinn <pat@mail.example.test>", "Application for Support Specialist"
    m.set_content("Hello, I am applying.")
    m.add_attachment(pdf, maintype="application", subtype="pdf", filename="cv.pdf")
    a = ingest.from_email(m.as_bytes(), {role["key"]: "Support Specialist"}, keep_unreadable=True)
    assert a.extra.get("resume_missing") and a.original == pdf
    ctx = c.app.state.ctx
    with ctx.factory() as s:
        r = s.scalars(select(Role)).first()
        app, status = intake.add_applicant(s, a, r, "mailbox", ctx.now(s), settings=ctx.settings)
        s.commit()
        assert status == "added" and s.scalars(select(ResumeFile).where(ResumeFile.application_id == app.id)).first() is not None


def test_a_crafted_page_with_hundreds_of_shapes_and_thousands_of_text_runs_is_followed_for_a_few_seconds_at_most():
    import time

    body = VISIBLE + "".join(f"0.{i % 9} g {i} {i} 5 5 re f\n" for i in range(300)) + "BT /F1 6 Tf 1 g 72 600 Td " + " ".join("(x) Tj" for _ in range(30000)) + " ET\n"
    started = time.perf_counter()
    got = read(body)
    assert time.perf_counter() - started < 8.0
    assert "Customer Support Specialist" in got.text
