"""Which SERP source a given configuration selects.

The important assertion here is the first one: the feature is dark until an
operator switches it on, in every environment, because it needs a search
instance that does not exist by default.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.serp.mock import MockSerpSource
from app.serp.registry import get_serp_source
from app.serp.searxng import SearxngSource


def _settings(**overrides):
    base = {
        "serp_enabled": False,
        "dry_run": True,
        "serp_base_url": "",
        "serp_language": "en",
        "serp_categories": "general",
        "serp_engines": "",
        "serp_safesearch": 0,
        "serp_timeout_seconds": 10.0,
        "serp_max_results": 20,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_disabled_by_default_yields_no_source():
    assert get_serp_source(_settings()) is None


def test_dry_run_uses_the_mock_so_ci_needs_no_instance():
    source = get_serp_source(_settings(serp_enabled=True, dry_run=True))
    assert isinstance(source, MockSerpSource)


def test_enabled_live_builds_the_searxng_source_from_settings():
    source = get_serp_source(
        _settings(
            serp_enabled=True,
            dry_run=False,
            serp_base_url="http://searxng:8080",
            serp_language="tr",
            serp_engines="google",
            serp_max_results=7,
        )
    )
    assert isinstance(source, SearxngSource)
    assert source.base_url == "http://searxng:8080"
    assert source.language == "tr"
    assert source.engines == "google"
    assert source.max_results == 7


def test_enabled_but_unconfigured_yields_no_source():
    """Better than a source that raises on every query.

    Six identical connection errors in the evidence table would read as an
    outage; no source at all reads as what it is — a missing setting.
    """
    assert get_serp_source(_settings(serp_enabled=True, dry_run=False)) is None
    assert get_serp_source(_settings(serp_enabled=True, dry_run=False, serp_base_url="  ")) is None


def test_dry_run_beats_a_configured_base_url():
    """DRY_RUN means $0 and no packets, whatever else is set."""
    source = get_serp_source(
        _settings(serp_enabled=True, dry_run=True, serp_base_url="http://searxng:8080")
    )
    assert isinstance(source, MockSerpSource)
