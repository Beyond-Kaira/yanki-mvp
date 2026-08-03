"""The SERP adapter against a REAL SearXNG instance.

Everything else in the suite mocks the HTTP layer, which proves we parse the
payload we *believe* SearXNG sends. This proves we parse the payload it actually
sends — the failure these tests exist to catch is an upstream release moving a
field, which no amount of respx can see.

Skipped unless ``SERP_TEST_BASE_URL`` points at an instance, so ``make test``
and the ordinary CI run stay hermetic. The `SERP` workflow sets it, after
booting a container federating exactly one engine: the fixture server in
``searxng/fixture_engine.py``. That determinism is the point — the public
engines refuse CI runners, so a test asserting real search results would be a
coin flip.
"""

from __future__ import annotations

import os

import pytest

from app.pipeline.kyc import KYC
from app.pipeline.serp_visibility import build_queries, detect, site_hosts
from app.serp.base import SerpUnavailable
from app.serp.searxng import SearxngSource
from tests.integration.searxng.fixture_engine import BRAND, BRAND_URL

BASE_URL = os.environ.get("SERP_TEST_BASE_URL", "")

pytestmark = pytest.mark.skipif(
    not BASE_URL, reason="set SERP_TEST_BASE_URL to run against a live SearXNG instance"
)


@pytest.fixture
def source() -> SearxngSource:
    return SearxngSource(BASE_URL)


@pytest.fixture
def kyc() -> KYC:
    return KYC(
        company=BRAND,
        industry="Robotics",
        category="warehouse robots",
        aliases=[BRAND, "Zendrix"],
        keywords=["warehouse robots"],
    )


def test_a_real_instance_answers_json_we_can_parse(source):
    page = source.search("best warehouse robots")

    assert page.query == "best warehouse robots"
    assert page.results, "the fixture engine should have returned results"
    assert [result.rank for result in page.results] == list(
        range(1, len(page.results) + 1)
    )
    assert all(result.url.startswith("http") for result in page.results)
    # Every result came from the one engine the instance federates.
    assert {result.engine for result in page.results} == {"fixture"}
    assert page.measurable is True


def test_the_brand_is_detected_through_the_real_response(source, kyc):
    page = source.search("best warehouse robots")

    hit = detect(page, kyc, site_hosts(BRAND_URL))

    assert hit is not None
    assert hit.rank == 1
    assert BRAND_URL.rstrip("/") in hit.url


def test_a_page_without_the_brand_is_a_real_miss(source, kyc):
    page = source.search("conveyor belts")

    assert page.results, "the fixture engine returns default results here"
    assert page.measurable is True
    assert detect(page, kyc, site_hosts(BRAND_URL)) is None


def test_an_empty_page_from_a_healthy_instance_stays_measurable(source):
    """Nothing ranked. That is an answer, and a miss is the honest reading."""
    page = source.search("__empty__ nothing ranks for this")

    assert page.results == ()
    assert page.unresponsive_engines == ()
    assert page.measurable is True


def test_a_failing_engine_makes_the_page_unmeasurable(source):
    """The honesty rule, proven against real SearXNG rather than a mock of it.

    The fixture engine is made to error, so SearXNG does what it does on an
    ordinary day when Brave rate-limits it: answers 200 with no results and the
    engine listed under ``unresponsive_engines``. That page must never be
    scoreable — reading it as "the brand ranks nowhere" invents a zero.
    """
    page = source.search("__boom__ make the engine fail")

    assert page.results == ()
    assert "fixture" in page.unresponsive_engines
    assert page.measurable is False


def test_queries_we_generate_are_accepted_by_a_real_instance(source, kyc):
    """Guards the seam between our query text and a real search endpoint."""
    queries = build_queries(kyc, 4)
    assert queries

    for query in queries:
        page = source.search(query)
        assert page.query == query


def test_a_wrong_base_url_is_reported_as_unavailable():
    """A 404 path must degrade, not raise something the worker cannot handle."""
    with pytest.raises(SerpUnavailable):
        SearxngSource(f"{BASE_URL}/definitely-not-searxng").search("anything")
