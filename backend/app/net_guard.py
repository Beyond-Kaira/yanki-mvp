"""Shared SSRF guard: reject URLs whose host resolves to a non-public address.

The submit endpoint is anonymous, and the discovery step fetches whatever URL is
submitted (following redirects), so without this guard an attacker could make the
worker reach loopback/private/link-local hosts or the cloud metadata endpoint
(169.254.169.254). This is used both at submit time (fast rejection) and inside
discovery's HTTP client, which re-checks every redirect hop — a public URL can
302 to a private one.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def is_public_host(host: str | None) -> bool:
    """True if every address ``host`` resolves to is public.

    Resolution failures are rejected. A worker must never turn a temporary DNS
    failure into permission to let another network stack resolve the host later.
    """
    if not host:
        return False
    host = host.strip("[]")  # IPv6 literals arrive bracketed
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if _ip_is_blocked(ip):
            return False
    return True


def is_public_url(url: str) -> bool:
    """True if ``url``'s host resolves only to public addresses."""
    return is_public_host(urlparse(url).hostname)
