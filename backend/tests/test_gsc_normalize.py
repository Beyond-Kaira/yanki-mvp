"""Reducing a Search Console property to something a project can be compared to.

This is the pure half of the feature and the half most worth pinning, because
every way it can be wrong is quiet. Too loose and a subdomain's report is
pre-pointed at the parent domain's traffic; too tight and a user's own property
never appears as the suggestion and they conclude the integration is broken.

The normalizer being *shared* with project creation is itself under test here:
several cases assert that a property reduces to exactly the ``domain_key`` that
``normalize_project_domain`` would have produced for the same site, so the two
sides cannot drift apart without something failing.
"""

from __future__ import annotations

import pytest

from app.gsc.normalize import (
    matches_project_domain,
    parse_property,
    property_type_of,
)
from app.services.seo_projects import normalize_project_domain


def _key(raw: str) -> str:
    return normalize_project_domain(raw).key


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("site_url", "expected_type", "expected_key"),
    [
        ("sc-domain:example.com", "domain", "example.com"),
        ("https://example.com/", "url_prefix", "example.com"),
        ("http://example.com/", "url_prefix", "example.com"),
        # www is stripped for identity, matching how a project keys itself.
        ("https://www.example.com/", "url_prefix", "example.com"),
        ("https://shop.example.com/", "url_prefix", "shop.example.com"),
        # A path-scoped prefix property is still the same site.
        ("https://example.com/blog/", "url_prefix", "example.com"),
        # Default ports vanish, non-default ports are part of the identity.
        ("https://example.com:443/", "url_prefix", "example.com"),
        ("http://localhost:8000/", "url_prefix", "localhost:8000"),
        ("https://example.com:8443/", "url_prefix", "example.com:8443"),
        ("  sc-domain:example.com  ", "domain", "example.com"),
        ("SC-DOMAIN:Example.COM", "domain", "example.com"),
    ],
)
def test_a_property_reduces_to_its_type_and_key(site_url, expected_type, expected_key):
    parsed = parse_property(site_url)

    assert parsed is not None
    assert parsed.property_type == expected_type
    assert parsed.domain_key == expected_key
    # The identifier itself is never rewritten: it is the API argument.
    assert parsed.site_url == site_url.strip()


@pytest.mark.parametrize(
    ("site_url", "equivalent_project_domain"),
    [
        ("sc-domain:example.com", "example.com"),
        ("https://www.example.com/", "https://www.example.com"),
        ("https://shop.example.com/", "shop.example.com"),
        ("http://localhost:8000/", "http://localhost:8000"),
    ],
)
def test_a_property_reduces_to_the_key_project_creation_would_have_produced(
    site_url, equivalent_project_domain
):
    """The anti-drift assertion. Two normalizers would fail this silently."""

    parsed = parse_property(site_url)

    assert parsed is not None
    assert parsed.domain_key == _key(equivalent_project_domain)


@pytest.mark.parametrize(
    "junk",
    [
        "",
        "   ",
        "sc-domain:",
        "sc-domain:   ",
        "not a url at all",
        "ftp://example.com/",
        "https:///no-host/",
    ],
)
def test_an_unreadable_identifier_is_dropped_rather_than_raising(junk):
    """One odd entry from Google costs that entry, not the whole list."""

    assert parse_property(junk) is None


def test_property_type_is_derived_from_the_prefix_alone():
    assert property_type_of("sc-domain:example.com") == "domain"
    assert property_type_of("https://example.com/") == "url_prefix"
    assert property_type_of("nonsense") == "url_prefix"


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "site_url",
    [
        "sc-domain:example.com",
        "https://example.com/",
        "http://example.com/",
        "https://www.example.com/",
        "http://www.example.com/",
        "https://example.com/blog/",
    ],
)
def test_every_spelling_of_the_same_site_matches(site_url):
    assert matches_project_domain(site_url, "example.com") is True


@pytest.mark.parametrize(
    "site_url",
    [
        # A Domain property really does cover this one — and suggesting it would
        # point a subdomain's report at the parent's traffic. Narrow on purpose.
        "sc-domain:example.com",
        "https://example.com/",
        "https://www.example.com/",
        "https://other.example.com/",
        "https://example.com.evil.test/",
        "https://notexample.com/",
    ],
)
def test_a_different_host_never_matches_a_subdomain_project(site_url):
    assert matches_project_domain(site_url, "shop.example.com") is False


def test_a_subdomain_property_matches_its_own_project():
    assert matches_project_domain("https://shop.example.com/", "shop.example.com") is True


def test_a_prefix_of_the_domain_is_not_a_match():
    """Substring logic would pass this. Host equality does not."""

    assert matches_project_domain("https://example.com/", "myexample.com") is False
    assert matches_project_domain("https://myexample.com/", "example.com") is False


def test_ports_are_part_of_identity():
    assert matches_project_domain("http://localhost:8000/", "localhost:8000") is True
    assert matches_project_domain("http://localhost:8000/", "localhost:9000") is False
    assert matches_project_domain("http://localhost:8000/", "localhost") is False


@pytest.mark.parametrize("junk", ["", "   ", "not a url", "sc-domain:"])
def test_an_unreadable_property_matches_nothing(junk):
    assert matches_project_domain(junk, "example.com") is False


@pytest.mark.parametrize("empty", ["", "   "])
def test_a_project_without_a_key_matches_nothing(empty):
    assert matches_project_domain("https://example.com/", empty) is False


def test_matching_is_case_insensitive_on_both_sides():
    assert matches_project_domain("https://EXAMPLE.com/", "example.com") is True
    assert matches_project_domain("SC-DOMAIN:Example.com", "EXAMPLE.COM") is True
