"""Shared adapter helpers: the SSRF guard for base URLs a person can set."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from sendora_core.adapters import AdapterError


_NAT64 = ipaddress.ip_network("64:ff9b::/96")


def _embedded_v4(ip):
    """The IPv4 address hidden inside an IPv6 one (mapped, 6to4 or NAT64), or None."""
    if ip.version != 6:
        return None
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    if ip.sixtofour is not None:
        return ip.sixtofour
    if ip in _NAT64:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def is_public(ip) -> bool:
    """True only for an address that is reachable on the public internet. Shared address space (100.64.0.0/10, which holds Tailscale hosts and some cloud metadata
    services), private, loopback, link local, multicast and reserved ranges are all refused, and so is an IPv6 address that wraps one of them."""
    inner = _embedded_v4(ip)
    if inner is not None and not is_public(inner):
        return False
    return bool(ip.is_global) and not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def check_url(url: str, *, allow_http_local: bool = False) -> tuple[str, list[str]]:
    """Refuse base URLs that point at the local network or non web schemes (SSRF guard for URLs a user can set).

    Only https is accepted. Hosts that resolve to private, loopback, link local or reserved addresses are refused,
    unless `allow_http_local` is set (tests and a self hosted tool on the same machine, a deliberate choice).
    Returns the cleaned URL and the addresses that were checked, so a caller that fetches can connect to one of THOSE addresses
    and not look the name up a second time (a name that answers a public address to the check and a private one to the connection is the classic bypass).
    """
    u = urlparse(url)
    if u.scheme not in {"https", "http"} or not u.hostname:
        raise AdapterError("The URL must start with https:// and include a host name.")
    if u.username or u.password:
        raise AdapterError("Put credentials in the key fields, not in the URL.")
    if u.scheme == "http" and not allow_http_local:
        raise AdapterError("Use an https:// URL.")
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise AdapterError(f"The host {u.hostname} could not be found.") from exc
    addresses: list[str] = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not is_public(ip) and not allow_http_local:
            raise AdapterError("That URL points at a private or local address, which is refused.")
        if str(ip) not in addresses:
            addresses.append(str(ip))
    return url.rstrip("/"), addresses


def safe_base_url(url: str, *, allow_http_local: bool = False) -> str:
    return check_url(url, allow_http_local=allow_http_local)[0]
