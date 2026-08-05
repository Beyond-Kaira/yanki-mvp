"""Canonical keys and anchor classification — the identity rules behind deltas.

A link's *identity* has to survive cosmetic churn. If ``https://blog.example/p``
and ``http://blog.example/p/?utm_source=x`` are two different links, then a
vendor tidying its URLs looks exactly like every one of those links dying and a
new one being born — a phantom new+lost pair per row, in the append-only event
log, on the day nothing actually happened.

So identity is a *key*: scheme dropped, host lowercased and de-``www``'d,
tracking parameters stripped, trailing slash normalized, fragment discarded. The
original URL is stored alongside for display; the key is what the unique
constraint and every diff use.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Parameters that identify a *campaign*, not a *page*. Stripping them is what
# stops one page from forking into a dozen identities.
_TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "gclid",
        "fbclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "ref",
        "referrer",
        "source",
    }
)

_GENERIC_ANCHORS = frozenset(
    {
        "click here",
        "here",
        "read more",
        "more",
        "link",
        "this",
        "this link",
        "website",
        "visit",
        "visit site",
        "learn more",
        "see more",
        "download",
        "homepage",
        "home",
    }
)

_URL_LIKE = re.compile(r"^(https?://|www\.)|^[a-z0-9-]+(\.[a-z0-9-]+)+/?$", re.I)


def domain_key(value: str) -> str:
    """Registrable-ish host key: lowercase, no scheme, no ``www.``, no port.

    Deliberately host-suffix based rather than true registrable-domain (which
    needs the public-suffix list). Tech-debt #37 already records that trade for
    the SERP matcher; this reuses the same rule so the two agree.
    """

    raw = (value or "").strip().lower()
    if not raw:
        return ""
    if "://" in raw:
        raw = urlsplit(raw).netloc or ""
    raw = raw.split("@")[-1].split("/")[0]
    if raw.startswith("[") and "]" in raw:  # IPv6 literal
        return raw[: raw.index("]") + 1]
    raw = raw.split(":")[0].strip(".")
    return raw[4:] if raw.startswith("www.") else raw


def url_key(value: str) -> str:
    """A stable identity key for one page.

    Scheme-insensitive on purpose: an http→https migration is the single most
    common way a whole backlink profile appears to die overnight.
    """

    raw = (value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"

    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw.lower()

    host = domain_key(parts.netloc)
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"

    query = urlencode(
        sorted(
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in _TRACKING_PARAMS
        )
    )
    # Fragment dropped entirely: it never identifies a different page to a
    # crawler, and vendors are inconsistent about keeping it.
    return urlunsplit(("", host, path, query, "")).lstrip("/") or host


def subnet_24(ip: str | None) -> str | None:
    """The /24 an IPv4 source sits in, for link-farm clustering. None if unknown."""

    if not ip:
        return None
    try:
        address = ipaddress.ip_address(ip.strip())
    except ValueError:
        return None
    if address.version != 4:
        return None
    octets = str(address).split(".")
    return ".".join(octets[:3]) + ".0/24"


def classify_anchor(anchor: str, *, brand: str, target_domain: str) -> str:
    """Bucket an anchor into the classes the distribution report uses.

    Order matters and is not arbitrary — ``empty`` before everything (an image
    link has no text), ``naked`` before ``brand`` (a bare URL containing the
    brand is still a naked link), and ``exact``/``partial`` last so a
    brand-containing money anchor reads as brand rather than exact.
    """

    text = (anchor or "").strip()
    if not text:
        return "empty"

    lowered = text.lower()
    if _URL_LIKE.match(lowered) or domain_key(lowered) == domain_key(target_domain):
        return "naked"
    if lowered in _GENERIC_ANCHORS:
        return "generic"

    brand_token = (brand or "").strip().lower()
    if brand_token and brand_token in lowered:
        return "brand"

    # Without a keyword set to compare against, "exact" cannot be claimed
    # honestly — a money anchor is distinguished from a partial one only by a
    # target keyword list this module does not have. Reporting everything left
    # as ``partial`` is the truthful floor; P8.3's keyword input refines it.
    return "partial"
