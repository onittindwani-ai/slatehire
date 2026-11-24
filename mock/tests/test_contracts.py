"""Contract tests: the adapters against excerpts of the vendors' public docs saved in mock/contracts/ (each SOURCE.txt says what was read, when, and what could not be read).

No machine readable spec was fetched for any vendor, so these are excerpts of page text, not the vendors' spec files. Where a page could not be read (Workable) or a part of it was not read
(Ashby paging, Greenhouse candidate fields) the field names stay UNVERIFIED and the tests only pin what the adapter sends. Nothing here ran against a real service.
"""

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from slatehire.adapters.ats import Ashby, Greenhouse
from slatehire.adapters.calendar import CalCom, GoogleCalendar
from sendora_core.settings import Mode

C = Path(__file__).resolve().parents[1] / "contracts"
WHEN = datetime(2026, 12, 4, 10, 0, tzinfo=timezone.utc)


def load(vendor, name):
    return json.loads((C / vendor / name).read_text(encoding="utf-8"))


def live(**kw):
    base = dict(mode=Mode.LIVE, kill_switch=False, allow_http_local_targets=False, ashby_api_key="ak", ashby_base_url="https://api.ashbyhq.com", greenhouse_token="gt", greenhouse_base_url="https://harvest.greenhouse.io",
                calcom_api_key="ck", calcom_event_type_id=123, calcom_base_url="https://api.cal.com/v2", google_access_token="gtok", google_calendar_id="primary", google_base_url="https://www.googleapis.com/calendar/v3")
    base.update(kw)
    return SimpleNamespace(**base)


def client(handler, base):
    return httpx.Client(base_url=base, transport=httpx.MockTransport(handler))


def test_every_contract_folder_says_where_it_came_from_and_when():
    folders = [d for d in C.iterdir() if d.is_dir()]
    assert {d.name for d in folders} >= {"calcom", "google_calendar", "ashby", "greenhouse", "workable", "smtp_imap"}
    for d in folders:
        t = (d / "SOURCE.txt").read_text(encoding="utf-8")
        assert "2026-11-23" in t and ("https://" in t or "NOT READ" in t), d.name


def test_calcom_booking_keeps_to_the_documented_header_and_required_fields():
    doc = load("calcom", "booking.json")
    seen = {}

    def handler(req):
        seen.update(m=req.method, p=req.url.path, h=req.headers, b=json.loads(req.content))
        return httpx.Response(200, json=doc["response_example"])

    out = CalCom(live(), client(handler, "https://api.cal.com/v2")).create_event(title="Interview", starts_at=WHEN, minutes=45, attendees=["cand@example.test", "i@example.test"], note="n", confirm=True)
    assert seen["m"] == "POST" and seen["p"].endswith("/bookings") and seen["h"]["cal-api-version"] == doc["header"]["cal-api-version"] and seen["h"]["authorization"].startswith("Bearer ")
    b = seen["b"]
    assert set(doc["request_required"]) <= set(b) and doc[("event_type_field")] in b and set(doc["attendee_required"]) <= set(b["attendee"]) and b["start"].endswith("Z")
    assert out["ref"] == doc["response_example"]["data"]["uid"]


def test_google_calendar_insert_keeps_to_the_documented_path_body_and_query():
    doc = load("google_calendar", "events_insert.json")
    seen = {}

    def handler(req):
        seen.update(m=req.method, p=req.url.path, q=dict(req.url.params), h=req.headers, b=json.loads(req.content))
        return httpx.Response(200, json={"id": "evt1", "kind": "calendar#event"})

    out = GoogleCalendar(live(), client(handler, "https://www.googleapis.com/calendar/v3")).create_event(title="Interview", starts_at=WHEN, minutes=30, attendees=["a@example.test"], note="n", confirm=True)
    assert seen["m"] == doc["method"] and seen["p"] == doc["path"].replace("{calendarId}", doc["calendar_id_primary"]) and seen["h"]["authorization"] == "Bearer gtok"
    assert set(doc["body_required"]) <= set(seen["b"]) and set(seen["b"]["start"]) <= set(doc["start_end_fields"]) and seen["b"]["start"]["dateTime"].endswith("Z")
    assert seen["q"]["sendUpdates"] in doc["query_optional"]["sendUpdates"]
    assert all("email" in a and set(a) <= set(doc["attendee_fields"]) for a in seen["b"]["attendees"]) and out["ref"] == "evt1"


def test_ashby_candidate_list_request_and_parsing_follow_the_page_where_it_was_read():
    doc = load("ashby", "candidate_list.json")
    seen = []

    def handler(req):
        seen.append((req.method, req.url.path, req.headers.get("authorization"), json.loads(req.content)))
        ex = doc["example_candidate"]
        return httpx.Response(200, json={"success": True, "results": [ex], "moreDataAvailable": False, "syncToken": "s"})

    got = Ashby(live(), client(handler, "https://api.ashbyhq.com")).list_applicants()
    method, path, auth, body = seen[0]
    assert method == doc["method"] and path == doc["path"] and auth == "Basic " + base64.b64encode(b"ak:").decode()
    assert set(body) <= set(doc["request_documented"]) | set(doc["request_not_confirmed"])  # cursor and limit are sent but NOT confirmed by the page we read
    assert got[0].name == "Adam Hart" and got[0].email == "adam.hart@example.com" and got[0].external_ref == doc["example_candidate"]["id"] and got[0].phone == ""


def test_greenhouse_uses_basic_auth_with_a_blank_password_and_follows_the_link_header():
    doc = load("greenhouse", "harvest.json")
    seen = []

    def handler(req):
        seen.append((req.url.path, req.headers["authorization"]))
        if len(seen) == 1:
            return httpx.Response(200, json=[{"id": 1, "first_name": "A", "last_name": "B", "email_addresses": [], "phone_numbers": [], "attachments": []}],
                                  headers={"Link": '<https://harvest.greenhouse.io/v1/candidates?page=abc&per_page=100>; rel="next"'})
        return httpx.Response(200, json=[])

    got = Greenhouse(live(), client(handler, "https://harvest.greenhouse.io")).list_applicants()
    assert doc["auth"].startswith("basic") and seen[0][1] == "Basic " + base64.b64encode(b"gt:").decode() and len(seen) == 2 and got[0].name == "A B"


def test_what_could_not_be_read_is_written_down_where_the_adapter_depends_on_it():
    gh = load("greenhouse", "harvest.json")
    assert "attachments" in gh["candidate_fields_not_confirmed"] and "2026-08-31" in gh["removal"]
    assert "nextCursor" in load("ashby", "candidate_list.json")["response_not_confirmed"]
    assert "NOT READ" in (C / "workable" / "SOURCE.txt").read_text()


@pytest.mark.parametrize("vendor", ["ashby", "greenhouse", "workable", "calcom", "google-calendar"])
def test_the_facts_file_of_each_vendor_points_to_its_contract_excerpt(vendor):
    text = (Path(__file__).resolve().parents[2] / "docs" / "facts" / f"{vendor}.md").read_text(encoding="utf-8")
    assert "mock/contracts/" in text
