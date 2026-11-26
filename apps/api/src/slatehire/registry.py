"""One registry of every adapter with its tier. Demo mode can only build the offline adapters."""

from __future__ import annotations

from slatehire.adapters.ats import Ashby, Greenhouse, SeedATS, Workable
from slatehire.adapters.calendar import CalCom, GoogleCalendar, SeedCalendar
from slatehire.adapters.handoff import BreezedocHandoff, PackageHandoff, SeedHandoff
from slatehire.adapters.mailbox import ImapMailbox, SeedMailbox
from sendora_core.adapters import AdapterError, AdapterRegistry, AdapterSpec

CATEGORIES = ("ats", "calendar", "mailbox", "handoff")
OFFLINE = {"seed", "package"}
ENV_VARS = {("ats", "ashby"): ["ASHBY_API_KEY"], ("ats", "workable"): ["WORKABLE_TOKEN", "WORKABLE_SUBDOMAIN"], ("ats", "greenhouse"): ["GREENHOUSE_TOKEN"],
            ("calendar", "calcom"): ["CALCOM_API_KEY", "CALCOM_EVENT_TYPE_ID"], ("calendar", "google"): ["GOOGLE_ACCESS_TOKEN"], ("mailbox", "imap"): ["IMAP_HOST", "IMAP_USER", "IMAP_PASSWORD"]}


def build_registry(settings) -> AdapterRegistry:
    reg = AdapterRegistry(settings)
    add = lambda c, n, t, f, notes="": reg.register(AdapterSpec(c, n, t, f, False, notes))  # noqa: E731
    add("ats", "seed", "A", SeedATS, "Offline demo. The demo loads its own applicants.")
    add("ats", "ashby", "B", Ashby, "Read only. candidate.list read from the Ashby docs on 2026-11-23. Local imitation only.")
    add("ats", "workable", "B", Workable, "Read only. Candidate list read from the Workable docs on 2026-11-23; the resume download step is UNVERIFIED. Local imitation only.")
    add("ats", "greenhouse", "B", Greenhouse, "Read only. Harvest v1 read from the Greenhouse docs on 2026-11-23; the docs announce its removal on 2026-08-31. Local imitation only.")
    add("calendar", "seed", "A", SeedCalendar, "Offline demo. The invite stays in the app.")
    add("calendar", "calcom", "B", CalCom, "POST /bookings with cal-api-version 2026-02-25, from the Cal.com docs on 2026-11-23. Local imitation only.")
    add("calendar", "google", "B", GoogleCalendar, "events.insert from the Google Calendar docs on 2026-11-23. Local imitation only.")
    add("mailbox", "seed", "A", SeedMailbox, "Offline demo.")
    add("mailbox", "imap", "A", ImapMailbox, "Plain IMAP, tested against the local mock mail server in mock/.")
    add("handoff", "seed", "A", SeedHandoff, "Offline demo.")
    add("handoff", "package", "A", PackageHandoff, "The default. Writes the approved offer to a file for your signing tool. Never sends.")
    add("handoff", "breezedoc", "C", BreezedocHandoff, "No live call built: the API could not be confirmed. Recipe in prompts/04-recipes.md.")
    return reg


def build_adapters(settings, registry=None) -> dict:
    reg = registry or build_registry(settings)
    out = {}
    for cat in CATEGORIES:
        name = getattr(settings, f"{cat}_adapter")
        if settings.demo_mode and name not in OFFLINE and not (cat == "mailbox" and name == "imap" and settings.imap_host in {"127.0.0.1", "localhost"}):
            raise AdapterError(f"DEMO_MODE is on, so only offline adapters can be used. Change {cat.upper()}_ADAPTER or turn DEMO_MODE off.")
        out[cat] = reg.get(cat, name)
    return out
