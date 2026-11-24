"""Fetch a resume from a web address. The only place the app downloads a URL a person typed, so every safeguard is here:
https only, no private or local addresses (unless a test or a self hosted setup turns that on), no redirects followed blindly, a size cap, a time limit."""

from __future__ import annotations

import httpx

from slatehire.adapters.base import safe_base_url
from sendora_core.adapters import AdapterError

MAX_BYTES = 5_000_000
MAX_REDIRECTS = 3


def safe_fetch(url: str, *, allow_http_local: bool = False, client: httpx.Client | None = None, headers: dict | None = None) -> bytes:
    cur = safe_base_url(url, allow_http_local=allow_http_local)
    own = client is None
    c = client or httpx.Client(timeout=20, follow_redirects=False)
    try:
        for _ in range(MAX_REDIRECTS + 1):
            with c.stream("GET", cur, headers=headers or {}) as r:
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    cur = safe_base_url(str(httpx.URL(cur).join(r.headers["location"])), allow_http_local=allow_http_local)  # every hop is checked again
                    continue
                if r.status_code != 200:
                    raise AdapterError(f"The address answered {r.status_code}.")
                buf = bytearray()
                for chunk in r.iter_bytes():
                    buf += chunk
                    if len(buf) > MAX_BYTES:
                        raise AdapterError("The file is larger than 5 MB.")
                return bytes(buf)
        raise AdapterError("Too many redirects.")
    except httpx.HTTPError as exc:
        raise AdapterError("The address could not be fetched.") from exc
    finally:
        if own:
            c.close()
