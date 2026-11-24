"""ATS adapters. READ ONLY: Slatehire pulls applicants in and never writes back, so a mistake here cannot move a candidate in your ATS.

Seed is offline. Ashby, Workable and Greenhouse are tier B: written from the vendors' public docs on 2026-11-23 and run only against local imitations in mock/ (UNVERIFIED live).
"""

from __future__ import annotations

import base64

import httpx

from slatehire.adapters.base import safe_base_url
from slatehire.adapters.fetch import safe_fetch
from slatehire.ingest import Applicant, IngestError, text_from_bytes
from sendora_core.adapters import AdapterError


def _resume(settings, url: str | None, name: str, headers: dict | None = None, client=None) -> str:
    if not url:
        return ""
    try:
        return text_from_bytes(safe_fetch(url, allow_http_local=settings.allow_http_local_targets, headers=headers, client=client), name)
    except (AdapterError, IngestError):
        return ""  # the applicant is still added; the resume can be pasted or uploaded


def _get(client: httpx.Client, method: str, path: str, **kw) -> httpx.Response:
    try:
        r = client.request(method, path, **kw)
    except httpx.HTTPError as exc:
        raise AdapterError("Could not reach the service.") from exc
    if r.status_code in (401, 403):
        raise AdapterError("The service refused the key.")
    if r.status_code == 429:
        raise AdapterError("The service says too many requests. Try again later.")
    r.raise_for_status()
    return r


class SeedATS:
    name = "seed"

    def __init__(self, settings):
        self.s = settings

    def list_applicants(self, limit: int = 200) -> list[Applicant]:
        return []

    def healthcheck(self):
        return True, "Offline demo adapter. The seed applicants are loaded by the demo, not pulled."


class Ashby:
    """POST /candidate.list with basic auth (key as user name, empty password), paged with moreDataAvailable and nextCursor."""

    name = "ashby"

    def __init__(self, settings, client: httpx.Client | None = None):
        if not settings.ashby_api_key:
            raise AdapterError("ASHBY_API_KEY is empty.")
        self.s = settings
        self.client = client or httpx.Client(base_url=safe_base_url(settings.ashby_base_url, allow_http_local=settings.allow_http_local_targets), timeout=30)
        self.auth = (settings.ashby_api_key, "")

    def list_applicants(self, limit: int = 200) -> list[Applicant]:
        out, cursor = [], None
        while len(out) < limit:
            body = {"limit": min(100, limit - len(out))} | ({"cursor": cursor} if cursor else {})
            data = _get(self.client, "POST", "/candidate.list", json=body, auth=self.auth).json()
            if not data.get("success", True):
                raise AdapterError("Ashby said no: " + str((data.get("errors") or ["unknown"])[0])[:120])
            for c in data.get("results", []):
                if c.get("doNotContact"):
                    continue
                handle = (c.get("resumeFileHandle") or {}).get("handle")
                text = ""
                if handle:
                    info = _get(self.client, "POST", "/file.info", json={"fileHandle": handle}, auth=self.auth).json().get("results", {})
                    text = _resume(self.s, info.get("url"), info.get("fileName", "resume.pdf"), client=self.client)
                out.append(Applicant(c.get("name", ""), (c.get("primaryEmailAddress") or {}).get("value", ""), (c.get("primaryPhoneNumber") or {}).get("value", ""), "", text, "", "ashby", external_ref=c.get("id")))
            cursor = data.get("nextCursor")
            if not data.get("moreDataAvailable") or not cursor:
                break
        return out

    def healthcheck(self):
        try:
            _get(self.client, "POST", "/candidate.list", json={"limit": 1}, auth=self.auth)
            return True, "Connected."
        except (AdapterError, httpx.HTTPError) as exc:
            return False, str(exc)


class Workable:
    """GET /spi/v3/candidates with a bearer token, paged with paging.next. The list gives only resume metadata, so the resume text needs the candidate detail (UNVERIFIED)."""

    name = "workable"

    def __init__(self, settings, client: httpx.Client | None = None):
        if not settings.workable_token or not (settings.workable_subdomain or settings.workable_base_url):
            raise AdapterError("WORKABLE_TOKEN and WORKABLE_SUBDOMAIN must both be set.")
        self.s = settings
        base = settings.workable_base_url or f"https://{settings.workable_subdomain}.workable.com/spi/v3"
        self.client = client or httpx.Client(base_url=safe_base_url(base, allow_http_local=settings.allow_http_local_targets), timeout=30)
        self.h = {"Authorization": f"Bearer {settings.workable_token}"}

    def list_applicants(self, limit: int = 200) -> list[Applicant]:
        out, path = [], "/candidates"
        params: dict | None = {"limit": min(100, limit)}
        while path and len(out) < limit:
            data = _get(self.client, "GET", path, params=params, headers=self.h).json()
            for c in data.get("candidates", []):
                if c.get("disqualified"):
                    continue
                text = ""
                if (c.get("resume_metadata") or {}).get("filename"):
                    det = _get(self.client, "GET", f"/candidates/{c['id']}", headers=self.h).json().get("candidate", {})
                    text = _resume(self.s, det.get("resume_url"), c["resume_metadata"]["filename"], client=self.client)
                out.append(Applicant(c.get("name", ""), c.get("email", ""), c.get("phone", ""), "", text, "", "workable", external_ref=str(c.get("id"))))
            nxt = (data.get("paging") or {}).get("next")
            path, params = (httpx.URL(nxt).raw_path.decode() if nxt else None), None
            if path and path.startswith("/spi/v3"):
                path = path[len("/spi/v3"):]
        return out

    def healthcheck(self):
        try:
            _get(self.client, "GET", "/candidates", params={"limit": 1}, headers=self.h)
            return True, "Connected."
        except (AdapterError, httpx.HTTPError) as exc:
            return False, str(exc)


class Greenhouse:
    """GET /v1/candidates with basic auth (token as user name, empty password), paged by the Link header. Attachments of type resume carry a short lived signed URL. The Harvest v1 and v2 API is announced for removal on 2026-08-31 (docs read 2026-11-23): check before you rely on it."""

    name = "greenhouse"

    def __init__(self, settings, client: httpx.Client | None = None):
        if not settings.greenhouse_token:
            raise AdapterError("GREENHOUSE_TOKEN is empty.")
        self.s = settings
        self.client = client or httpx.Client(base_url=safe_base_url(settings.greenhouse_base_url, allow_http_local=settings.allow_http_local_targets), timeout=30)
        self.h = {"Authorization": "Basic " + base64.b64encode(f"{settings.greenhouse_token}:".encode()).decode()}

    def list_applicants(self, limit: int = 200) -> list[Applicant]:
        out, url, params = [], "/v1/candidates", {"per_page": min(100, limit)}
        while url and len(out) < limit:
            r = _get(self.client, "GET", url, params=params, headers=self.h)
            for c in r.json():
                att = next((a for a in c.get("attachments", []) if a.get("type") == "resume"), None)
                text = _resume(self.s, att.get("url"), att.get("filename", "resume.pdf"), client=self.client) if att else ""
                email = next((e.get("value", "") for e in c.get("email_addresses", [])), "")
                phone = next((p.get("value", "") for p in c.get("phone_numbers", [])), "")
                out.append(Applicant(f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(), email, phone, "", text, "", "greenhouse", external_ref=str(c.get("id"))))
            nxt = r.links.get("next", {}).get("url")
            url, params = (httpx.URL(nxt).raw_path.decode() + ("?" + httpx.URL(nxt).query.decode() if httpx.URL(nxt).query else "") if nxt else None), None
        return out

    def healthcheck(self):
        try:
            _get(self.client, "GET", "/v1/candidates", params={"per_page": 1}, headers=self.h)
            return True, "Connected."
        except (AdapterError, httpx.HTTPError) as exc:
            return False, str(exc)
