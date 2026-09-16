"""Domain rank-check for keyword preview."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.keyword.rank_check import check_keyword_ranks, normalize_rank_domain
from app.keyword.registry import get_keyword_serp_source
from app.serp.base import SerpPage, SerpResult
from app.serp.dataforseo import page_from_api_payload
from app.serp.mock import MOCK_DOMAIN, MockSerpSource

DATAFORSEO_FIXTURE = (
    Path(__file__).resolve().parents[1] / "serp" / "fixtures" / "dataforseo_organic.json"
)


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


def test_check_keyword_ranks_hits_dataforseo_fixture_domain():
    payload = json.loads(DATAFORSEO_FIXTURE.read_text())
    page = page_from_api_payload(payload, query="best crm software", max_results=20)

    class _DfsSerp:
        name = "dataforseo"
        language = "en"

        def search(self, query: str) -> SerpPage:
            return page

    domain, hits = check_keyword_ranks(
        _DfsSerp(),  # type: ignore[arg-type]
        domain="acmecrm.example",
        queries=["best crm software"],
    )
    assert domain == "acmecrm.example"
    assert len(hits) == 1
    assert hits[0].measurable is True
    assert hits[0].appeared is True
    assert hits[0].rank == 1
    assert hits[0].matched_url == "https://www.acmecrm.example/"


def test_rank_check_uses_keyword_registry_dataforseo_without_serp_enabled():
    source = get_keyword_serp_source(
        SimpleNamespace(
            keyword_enabled=True,
            dry_run=False,
            serp_enabled=False,
            serp_provider="dataforseo",
            dataforseo_login="user@example.com",
            dataforseo_password="secret",
            serp_language="en",
            serp_categories="general",
            serp_engines="",
            serp_safesearch=0,
            serp_timeout_seconds=10.0,
            serp_max_results=20,
            dataforseo_location_code=0,
            dataforseo_device="desktop",
            serp_base_url="",
        )
    )
    assert source is not None
    assert source.name == "dataforseo"
