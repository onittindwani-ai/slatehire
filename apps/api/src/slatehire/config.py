"""Slatehire settings. Names only in docs, never values."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from sendora_core.settings import BaseAppSettings


class Settings(BaseAppSettings):
    app_name: str = "slatehire"
    database_url: str = "sqlite:///./slatehire.sqlite3"
    owner_email: str = "owner@example.test"
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
    fairness_min_group: int = 10
    fairness_threshold: str = "4/5"
    redact_institutions: bool = True
    blind_default: bool = True
    min_scorecards: int = 2
    application_webhook_secret: str = ""

    def problems(self) -> list[str]:
        out = [p for p in super().problems() if not (self.demo_mode and p.startswith("MODE is live while DEMO_MODE"))]
        if not self.demo_mode and not self.owner_password_hash:
            out.append("OWNER_PASSWORD_HASH is empty. Create one with tools/hash_password.py and set it before you run outside demo mode.")
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
