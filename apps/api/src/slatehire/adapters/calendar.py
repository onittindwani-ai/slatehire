"""Calendar adapters. Creating an event invites a real person, so it is a write: it needs live mode and an explicit confirm.

Seed keeps the invite inside the app. Cal.com v2 and Google Calendar are tier B: from the vendors' docs on 2026-11-23, run only against local imitations (UNVERIFIED live).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from slatehire.adapters.base import safe_base_url
from sendora_core.adapters import AdapterError
from sendora_core.safety import guard_write

CALCOM_VERSION = "2026-02-25"  # the cal-api-version header value shown in the Cal.com bookings docs on 2026-11-23


def _check(settings, confirm: bool, action: str) -> None:
    if not confirm:
        raise AdapterError("Sending an invite needs an explicit confirm. Nothing was sent.")
    guard_write(settings, action)


class SeedCalendar:
    name = "seed"

    def __init__(self, settings):
        self.s = settings

    def create_event(self, *, title: str, starts_at: datetime, minutes: int, attendees: list[str], note: str, confirm: bool) -> dict:
        return {"ref": f"seed-{int(starts_at.timestamp())}", "detail": "Offline demo: the invite stays inside the app. Nothing is sent."}

    def healthcheck(self):
        return True, "Offline demo adapter."


class CalCom:
    name = "calcom"

    def __init__(self, settings, client: httpx.Client | None = None):
        if not settings.calcom_api_key or not settings.calcom_event_type_id:
            raise AdapterError("CALCOM_API_KEY and CALCOM_EVENT_TYPE_ID must both be set.")
        self.s = settings
        self.client = client or httpx.Client(base_url=safe_base_url(settings.calcom_base_url, allow_http_local=settings.allow_http_local_targets), timeout=30)

    def _h(self):
        return {"Authorization": f"Bearer {self.s.calcom_api_key}", "cal-api-version": CALCOM_VERSION}

    def create_event(self, *, title: str, starts_at: datetime, minutes: int, attendees: list[str], note: str, confirm: bool) -> dict:
        _check(self.s, confirm, "calcom.create_booking")
        if not attendees:
            raise AdapterError("A booking needs at least one attendee email.")
        body = {"start": starts_at.strftime("%Y-%m-%dT%H:%M:%SZ"), "eventTypeId": self.s.calcom_event_type_id, "lengthInMinutes": minutes,
                "attendee": {"name": attendees[0].split("@")[0], "email": attendees[0], "timeZone": "UTC"}, "guests": attendees[1:], "metadata": {"purpose": title[:80]}}
        r = self.client.post("/bookings", json=body, headers=self._h())
        if r.status_code in (401, 403):
            raise AdapterError("Cal.com refused the key.")
        r.raise_for_status()
        d = r.json().get("data", {})
        return {"ref": str(d.get("uid") or d.get("id", "")), "detail": "Booked in Cal.com."}

    def healthcheck(self):
        try:
            r = self.client.get("/me", headers=self._h())
            return (True, "Connected.") if r.status_code == 200 else (False, "Cal.com refused the key." if r.status_code in (401, 403) else f"Cal.com answered {r.status_code}.")
        except httpx.HTTPError:
            return False, "Could not reach Cal.com."


class GoogleCalendar:
    """POST /calendars/{id}/events with a bearer access token. sendUpdates=all, so Google tells the guests (the docs list all, externalOnly and none)."""

    name = "google"

    def __init__(self, settings, client: httpx.Client | None = None):
        if not settings.google_access_token:
            raise AdapterError("GOOGLE_ACCESS_TOKEN is empty.")
        self.s = settings
        self.client = client or httpx.Client(base_url=safe_base_url(settings.google_base_url, allow_http_local=settings.allow_http_local_targets), timeout=30)

    def create_event(self, *, title: str, starts_at: datetime, minutes: int, attendees: list[str], note: str, confirm: bool) -> dict:
        _check(self.s, confirm, "google.create_event")
        end = starts_at + timedelta(minutes=minutes)
        body = {"summary": title, "description": note, "start": {"dateTime": starts_at.strftime("%Y-%m-%dT%H:%M:%SZ")}, "end": {"dateTime": end.strftime("%Y-%m-%dT%H:%M:%SZ")}, "attendees": [{"email": a} for a in attendees]}
        r = self.client.post(f"/calendars/{self.s.google_calendar_id}/events", params={"sendUpdates": "all"}, json=body, headers={"Authorization": f"Bearer {self.s.google_access_token}"})
        if r.status_code in (401, 403):
            raise AdapterError("Google refused the access token.")
        r.raise_for_status()
        return {"ref": str(r.json().get("id", "")), "detail": "Event created in Google Calendar."}

    def healthcheck(self):
        try:
            r = self.client.get(f"/calendars/{self.s.google_calendar_id}", headers={"Authorization": f"Bearer {self.s.google_access_token}"})
            return (True, "Connected.") if r.status_code == 200 else (False, "Google refused the token." if r.status_code in (401, 403) else f"Google answered {r.status_code}.")
        except httpx.HTTPError:
            return False, "Could not reach Google Calendar."
