"""Keyword Ads metrics seam tests."""

from __future__ import annotations

from types import SimpleNamespace

from app.keyword.base import KeywordIdea
from app.keyword.metrics.enrich import enrich_ideas_with_metrics
from app.keyword.metrics.google_ads import _rows_from_historical_metrics_response
from app.keyword.metrics.locale_map import ads_language_and_geo_for_locale
from app.keyword.metrics.mock import MockKeywordMetricsSource
from app.keyword.metrics.registry import get_keyword_metrics_source


def test_ads_locale_map_known_and_fallback():
    lang, geo = ads_language_and_geo_for_locale("en-GB")
    assert "1000" in lang
    assert "2826" in geo
    lang_tr, geo_tr = ads_language_and_geo_for_locale("tr")
    assert "1037" in lang_tr
    assert "2792" in geo_tr
    lang_fallback, _ = ads_language_and_geo_for_locale("xx-unknown")
    assert "1000" in lang_fallback


def test_mock_metrics_lookup_is_deterministic():
    source = MockKeywordMetricsSource()
    rows = source.lookup(["money transfer", "money transfer", "  CRM  "])
    assert len(rows) == 2
    assert rows[0].avg_monthly_searches is not None
    assert rows[0].metrics_estimated is False
    assert rows[0].provider == "mock"


def test_enrich_ideas_sets_volume_and_clears_estimated_flag():
    ideas = (
        KeywordIdea(
            phrase="money transfer",
            source="seed",
            signals={"volume_estimated": True, "estimated_demand_score": 52},
        ),
    )
    enriched = enrich_ideas_with_metrics(ideas, MockKeywordMetricsSource(), locale="en")
    assert len(enriched) == 1
    signals = enriched[0].signals
    assert signals["volume_estimated"] is False
    assert isinstance(signals["volume"], int)
    assert signals["metrics_provider"] == "mock"
    assert signals["estimated_demand_score"] == 52


def test_registry_off_without_flag():
    assert get_keyword_metrics_source(SimpleNamespace(keyword_ads_enabled=False)) is None


def test_registry_mock_under_dry_run():
    source = get_keyword_metrics_source(SimpleNamespace(keyword_ads_enabled=True, dry_run=True))
    assert isinstance(source, MockKeywordMetricsSource)


def test_registry_none_when_live_but_credentials_missing():
    assert (
        get_keyword_metrics_source(
            SimpleNamespace(
                keyword_ads_enabled=True,
                dry_run=False,
                google_ads_developer_token="",
                google_ads_client_id="",
                google_ads_client_secret="",
                google_ads_refresh_token="",
                google_ads_customer_id="",
                google_ads_login_customer_id="",
            )
        )
        is None
    )


def test_parse_historical_metrics_response():
    payload = {
        "results": [
            {
                "text": "money transfer",
                "keywordMetrics": {
                    "avgMonthlySearches": 12100,
                    "competition": "HIGH",
                    "competitionIndex": 88,
                    "lowTopOfPageBidMicros": 1000000,
                    "highTopOfPageBidMicros": 2500000,
                },
            }
        ]
    }
    rows = _rows_from_historical_metrics_response(payload, provider="google_ads")
    assert len(rows) == 1
    assert rows[0].avg_monthly_searches == 12100
    assert rows[0].competition == "HIGH"
    assert rows[0].provider == "google_ads"
