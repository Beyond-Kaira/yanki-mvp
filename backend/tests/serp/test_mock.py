"""The DRY_RUN SERP source: deterministic, offline, and about half hits."""

from __future__ import annotations

from app.providers.mock import MOCK_COMPANY
from app.serp.base import SerpPage
from app.serp.mock import MOCK_DOMAIN, MockSerpSource


def test_is_deterministic_for_the_same_query():
    source = MockSerpSource()
    assert source.search("best robots") == source.search("best robots")


def test_a_hit_puts_the_mock_company_first_on_its_own_domain():
    source = MockSerpSource()
    # Find a query the hash makes a hit, so the assertion does not depend on
    # which particular string happens to land on which side.
    page = next(
        p
        for p in (source.search(f"query {i}") for i in range(20))
        if MOCK_COMPANY in p.results[0].title
    )
    assert page.results[0].rank == 1
    assert MOCK_DOMAIN in page.results[0].url


def test_every_page_carries_filler_competitors():
    page = MockSerpSource().search("best robots")
    assert len(page.results) >= 4
    assert any("Acme" in result.title for result in page.results)


def test_ranks_are_contiguous_from_one():
    page = MockSerpSource().search("best robots")
    assert [r.rank for r in page.results] == list(range(1, len(page.results) + 1))


def test_never_declares_itself_unmeasurable():
    """CI runs on this source; a randomly-unmeasurable mock would be flaky."""
    for i in range(20):
        page: SerpPage = MockSerpSource().search(f"query {i}")
        assert page.measurable is True
        assert page.unresponsive_engines == ()


def test_roughly_half_the_queries_rank_the_company():
    source = MockSerpSource()
    hits = sum(
        1 for i in range(100) if MOCK_COMPANY in source.search(f"query {i}").results[0].title
    )
    assert 25 < hits < 75
