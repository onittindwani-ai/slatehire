"""Fetch a resume from a web address. The only place the app downloads a URL a person typed, so every safeguard is here:
https only, no private or local addresses (unless a test or a self hosted setup turns that on), no redirects followed blindly, a size cap, an overall time limit,
and the connection goes to the address that was checked (the name is looked up once, not twice)."""

from __future__ import annotations

import time

import httpx

from slatehire.adapters.base import check_url
from sendora_core.adapters import AdapterError

MAX_BYTES = 5_000_000
MAX_REDIRECTS = 3
MAX_SECONDS = 30.0  # for the whole download, however slowly the server sends it


def _pinned(url: str, ip: str) -> tuple[httpx.URL, dict, dict]:
    """The same request, sent to the checked address. The Host header and the TLS name stay the real ones, so the certificate is still checked against the name."""
    real = httpx.URL(url)
    host = real.host
    default_port = 443 if real.scheme == "https" else 80
    host_header = host if real.port in (None, default_port) else f"{host}:{real.port}"
    target = real.copy_with(host=ip)
    return target, {"Host": host_header}, ({"sni_hostname": host} if real.scheme == "https" else {})


def safe_fetch(url: str, *, allow_http_local: bool = False, client: httpx.Client | None = None, headers: dict | None = None) -> bytes:
    cur, addresses = check_url(url, allow_http_local=allow_http_local)
    own = client is None
    c = client or httpx.Client(timeout=20, follow_redirects=False)
    started = time.monotonic()
    try:
        for _ in range(MAX_REDIRECTS + 1):
            target, extra, ext = (httpx.URL(cur), {}, {}) if allow_http_local else _pinned(cur, addresses[0])
            with c.stream("GET", target, headers={**(headers or {}), **extra}, extensions=ext) as r:
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    cur, addresses = check_url(str(httpx.URL(cur).join(r.headers["location"])), allow_http_local=allow_http_local)  # every hop is checked again
                    continue
                if r.status_code != 200:
                    raise AdapterError(f"The address answered {r.status_code}.")
                buf = bytearray()
                for chunk in r.iter_bytes():
                    buf += chunk
                    if len(buf) > MAX_BYTES:
                        raise AdapterError("The file is larger than 5 MB.")
                    if time.monotonic() - started > MAX_SECONDS:
                        raise AdapterError("The address was too slow to answer.")
                return bytes(buf)
        raise AdapterError("Too many redirects.")
    except httpx.HTTPError as exc:
        raise AdapterError("The address could not be fetched.") from exc
    finally:
        if own:
            c.close()
