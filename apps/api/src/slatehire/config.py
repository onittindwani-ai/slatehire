"""Slatehire settings. Names only in docs, never values."""

from __future__ import annotations

import ipaddress
from typing import Literal

from pydantic import Field

from sendora_core.settings import BaseAppSettings, Mode

DEFAULT_OWNER_EMAIL = "owner@example.test"
DEFAULT_COMPANY_NAME = "Example Company"


def is_loopback(host: str) -> bool:
    """True for a mail server on this same computer. A host name other than localhost is never trusted to be local."""
    if (host or "").strip().lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address((host or "").strip().strip("[]")).is_loopback
    except ValueError:
        return False


class Settings(BaseAppSettings):
    app_name: str = "slatehire"
    database_url: str = "sqlite:///./slatehire.sqlite3"
    owner_email: str = DEFAULT_OWNER_EMAIL
    # Who the offers and the job posts speak for. The default is a placeholder: problems() lists it and a live start outside demo mode is refused until it is your company.
    company_name: str = Field(default=DEFAULT_COMPANY_NAME, max_length=120)  # COMPANY_NAME
    owner_password_hash: str | None = None
    approver_email: str | None = None
    approver_password_hash: str | None = None
    viewer_email: str | None = None  # a read only sign in (for example a hiring manager who only looks); it can never change anything
    viewer_password_hash: str | None = None
    members_json: str = ""  # optional extra sign ins: [{"email": "...", "password_hash": "...", "role": "approver" or "viewer"}]
    login_burst: int = Field(default=5, ge=1, le=1000)  # sign in tries in a row before a short wait; the browser tests raise it

    seed_dir: str = ""
    export_dir: str = "./exports"
    upload_max_bytes: int = 5_000_000

    ats_adapter: str = "seed"  # seed, ashby, workable, greenhouse
    ashby_api_key: str = ""
    ashby_base_url: str = "https://api.ashbyhq.com"
    workable_token: str = ""
    workable_subdomain: str = ""
    workable_base_url: str = ""
    greenhouse_token: str = ""
    greenhouse_base_url: str = "https://harvest.greenhouse.io"
    calendar_adapter: str = "seed"  # seed, calcom, google
    calcom_api_key: str = ""
    calcom_event_type_id: int = 0
    calcom_base_url: str = "https://api.cal.com/v2"
    google_access_token: str = ""
    google_calendar_id: str = "primary"
    google_base_url: str = "https://www.googleapis.com/calendar/v3"
    mailbox_adapter: str = "seed"  # seed, imap
    handoff_adapter: str = "package"  # package, seed
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""
    imap_use_ssl: bool = True
    allow_http_local_targets: bool = False
    scorer: Literal["rules", "model"] = "rules"  # SCORER=model scores one criterion at a time with the model, only when LLM_BACKEND is fixture or anthropic; the quote and total checks run either way

    # Decided defaults (owner decision, 2026-11-23). The implementer can change every one, in the app or in the environment.
    retention_days: int = 365
    fairness_min_group: int = Field(default=10, ge=2, le=200)  # a group smaller than this is never compared and its counts are never shown
    fairness_threshold: str = "4/5"
    redact_institutions: bool = True
    blind_default: bool = True
    min_scorecards: int = 2
    open_retention_days: int = Field(default=730, ge=0)  # OPEN_RETENTION_DAYS: days after which the personal data of an applicant nobody decided on is deleted (0 means never)
    application_webhook_secret: str = ""
    proxy_terms: str = ""  # PROXY_TERMS: comma separated words a rubric may not look for (for example age, school or language proxies); the built in list is always checked too

    def identity_problems(self) -> list[str]:
        """What is still a placeholder. An offer file carries the company name and the owner signs in with the owner address, so both must be real before live use."""
        out: list[str] = []
        if self.owner_email.strip().lower() == DEFAULT_OWNER_EMAIL:
            out.append("OWNER_EMAIL is still the example address. Set the address the owner signs in with.")
        if self.company_name.strip() in {"", DEFAULT_COMPANY_NAME}:
            out.append("COMPANY_NAME is still the placeholder. Set your company name: it is written into every offer file and job post.")
        return out

    def runtime_errors(self) -> list[str]:
        out = super().runtime_errors()
        if self.mode is Mode.LIVE and not self.demo_mode:
            out += self.identity_problems()
        if self.mailbox_adapter == "imap" and not self.imap_use_ssl and not is_loopback(self.imap_host):
            out.append("IMAP_USE_SSL=false is only allowed for a mail server on this same computer (127.0.0.1). The mailbox password would cross the network in clear text. Turn it back on.")
        return list(dict.fromkeys(out))

    def proxy_term_list(self) -> list[str]:
        return [t.strip().lower() for t in self.proxy_terms.split(",") if t.strip()]

    def problems(self) -> list[str]:
        out = list(super().problems())  # includes "MODE is live while DEMO_MODE is true": a demo never leaves draft mode (see Ctx.effective), and the page says so
        if not self.demo_mode and not self.owner_password_hash:
            out.append("OWNER_PASSWORD_HASH is empty. Create one with tools/hash_password.py and set it before you run outside demo mode.")
        if self.demo_mode and self.owner_password_hash:
            out.append("DEMO_MODE is true but an owner password is set. The public demo password is switched off; set DEMO_MODE=false for a real install.")
        if not self.demo_mode:
            out += [p for p in self.identity_problems() if p not in out]
            if not (self.approver_email or self.members_json):
                out.append("No second person can sign in (APPROVER_EMAIL or MEMBERS_JSON is empty), so no offer can be approved: the person who writes the terms cannot approve them.")
            if self.allow_http_local_targets:
                out.append("ALLOW_HTTP_LOCAL_TARGETS is true, so the address guard no longer stops a resume link or an ATS address from reaching your private network. Use it on a test machine only.")
        need = {("ats", "ashby"): (self.ashby_api_key, "ASHBY_API_KEY"), ("ats", "workable"): (self.workable_token, "WORKABLE_TOKEN"), ("ats", "greenhouse"): (self.greenhouse_token, "GREENHOUSE_TOKEN"),
                ("calendar", "calcom"): (self.calcom_api_key, "CALCOM_API_KEY"), ("calendar", "google"): (self.google_access_token, "GOOGLE_ACCESS_TOKEN"), ("mailbox", "imap"): (self.imap_password, "IMAP_PASSWORD")}
        for (cat, name), (val, var) in need.items():
            if getattr(self, f"{cat}_adapter") == name and not val:
                out.append(f"{cat.upper()}_ADAPTER is {name} but {var} is empty.")
        if self.scorer == "model" and self.effective_llm_backend.value == "offline":
            out.append("SCORER is model but LLM_BACKEND is offline, so the rules score. Set LLM_BACKEND to fixture or anthropic, or SCORER back to rules.")
        if self.retention_days < 30:
            out.append("RETENTION_DAYS is under 30. Check the law that applies to your records before you keep data for so short a time.")
        return out
