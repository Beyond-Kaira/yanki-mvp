"""Domain rank-check for keyword preview."""

from __future__ import annotations

from app.keyword.rank_check import check_keyword_ranks, normalize_rank_domain
from app.serp.base import SerpPage, SerpResult
from app.serp.mock import MOCK_DOMAIN, MockSerpSource


def test_normalize_rank_domain_accepts_bare_host_and_url():
    assert normalize_rank_domain("Example.COM") == "example.com"
    assert normalize_rank_domain("https://www.example.com/path") == "example.com"


def test_check_keyword_ranks_against_mock_serp():
    source = MockSerpSource()
    # Mock ranks MOCK_DOMAIN on roughly half of queries; use several and assert shape.
    domain, hits = check_keyword_ranks(
        source,
        domain=MOCK_DOMAIN,
        queries=["alpha CRM", "beta CRM", "gamma CRM", "delta CRM"],
        max_queries=4,
    )
    assert domain == MOCK_DOMAIN
    assert len(hits) == 4
    for hit in hits:
        assert hit.measurable is True
        assert hit.appeared in (True, False)
        if hit.appeared:
            assert hit.rank is not None
            assert hit.matched_via == "domain"
            assert MOCK_DOMAIN in (hit.matched_url or "")


def test_check_keyword_ranks_reports_miss_for_other_domain():
    page = SerpPage(
        query="widgets",
        results=(SerpResult(rank=1, url="https://other.example/a", title="a"),),
    )

    class _Fixed:
        name = "fixed"
        language = "en"

        def search(self, query: str) -> SerpPage:
            return page

    domain, hits = check_keyword_ranks(
        _Fixed(),  # type: ignore[arg-type]
        domain="yankidemo.co",
        queries=["widgets"],
    )
    assert domain == "yankidemo.co"
    assert hits[0].appeared is False
    assert hits[0].rank is None
