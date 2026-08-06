"""Turning a Search Console property identifier into something comparable.

Google names a property in one of two ways, and they do not look alike::

    sc-domain:example.com      a Domain property, all subdomains, all protocols
    https://www.example.com/   a URL-prefix property, that scheme and host only

A Site Audit project, meanwhile, is identified by ``SeoProject.domain_key`` —
lowercase host, ``www.`` removed, port kept only when it is not the scheme's
default. To decide whether a property is *the* property for a project, both
sides have to be reduced to the same thing.

**This module does not invent that reduction.** It feeds the URL form straight
through :func:`app.services.seo_projects.normalize_project_domain`, the same
function that produced ``domain_key`` when the project was created. That is a
deliberate choice against convenience: ``app/services/backlinks.py`` carries a
docstring about exactly this hazard — "a read that normalizes differently from
the write silently returns an empty profile" — and a second, nearly-identical
host normalizer is how that happens. Here the failure would be quieter still: a
user's own property simply never appears as the suggested one, and nobody can
tell whether that is a bug or just Google.

**Matching is exact on the host, and deliberately narrow.** A Domain property
for ``example.com`` really does cover ``shop.example.com``, so treating it as a
match for a ``shop.example.com`` project would be *technically* defensible — and
wrong here. Suggesting a property means pre-selecting which numbers a customer
is about to read, and silently pointing a subdomain's report at the parent
domain's traffic is a worse error than showing no suggestion at all. The user
can still choose it: matching only orders and flags the list, it never filters
it, and it never binds anything on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.seo_projects import InvalidProjectDomain, normalize_project_domain

DOMAIN_PROPERTY_PREFIX = "sc-domain:"

PropertyType = Literal["domain", "url_prefix"]


@dataclass(frozen=True, slots=True)
class ParsedProperty:
    """A property identifier, reduced to something a project can be compared to."""

    # Exactly as Google named it. Stored and sent back untouched, because it is
    # the argument every later Search Console call needs.
    site_url: str
    property_type: PropertyType
    # Comparable to SeoProject.domain_key, or "" when the identifier could not
    # be understood at all.
    domain_key: str


def parse_property(site_url: str) -> ParsedProperty | None:
    """Reduce one Search Console property identifier, or ``None`` if it is junk.

    ``None`` rather than an exception: this runs over a list Google returned, and
    one unfamiliar entry should cost that entry, not the whole page.
    """

    value = (site_url or "").strip()
    if not value:
        return None

    if value.lower().startswith(DOMAIN_PROPERTY_PREFIX):
        property_type: PropertyType = "domain"
        # A Domain property has no scheme. normalize_project_domain adds https
        # for a bare host, so the same function still applies — which is the
        # point of routing both forms through it.
        candidate = value[len(DOMAIN_PROPERTY_PREFIX) :].strip()
    else:
        property_type = "url_prefix"
        candidate = value

    if not candidate:
        return None

    try:
        normalized = normalize_project_domain(candidate)
    except InvalidProjectDomain:
        return None

    return ParsedProperty(
        site_url=value,
        property_type=property_type,
        domain_key=normalized.key,
    )


def property_type_of(site_url: str) -> PropertyType:
    """The kind of property, for storing alongside a link.

    Falls back to ``url_prefix`` for anything without the domain prefix, which
    is what every non-Domain property is.
    """

    return (
        "domain"
        if (site_url or "").strip().lower().startswith(DOMAIN_PROPERTY_PREFIX)
        else "url_prefix"
    )


def matches_project_domain(site_url: str, project_domain_key: str) -> bool:
    """Is this property the obvious one for a project on ``project_domain_key``?

    Exact host equality after both sides go through the project normalizer, so
    ``https://www.example.com/`` matches a project keyed ``example.com`` and
    ``https://shop.example.com/`` does not. A path-scoped prefix property still
    matches on host — narrowing by path is a choice about *what* to report, not
    about which site it is.
    """

    parsed = parse_property(site_url)
    if parsed is None or not parsed.domain_key or not project_domain_key:
        return False

    return parsed.domain_key == project_domain_key.strip().lower()
