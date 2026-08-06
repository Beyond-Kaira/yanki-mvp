"""Which keyword source a given configuration selects.

Live/product path is SearXNG. Mock only under DRY_RUN. Feature dark until
``KEYWORD_ENABLED``.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.keyword.mock import MockKeywordSource
from app.keyword.registry import get_keyword_source
from app.keyword.searxng_expand import SearxngKeywordSource


def _settings(**overrides):
    base = {
        "keyword_enabled": False,
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
    assert get_keyword_source(_settings()) is None


def test_dry_run_uses_the_mock_so_ci_needs_no_instance():
    source = get_keyword_source(_settings(keyword_enabled=True, dry_run=True))
    assert isinstance(source, MockKeywordSource)


def test_enabled_live_builds_the_searxng_keyword_source():
    source = get_keyword_source(
        _settings(
            keyword_enabled=True,
            dry_run=False,
            serp_base_url="http://searxng:8080",
            serp_language="tr",
        )
    )
    assert isinstance(source, SearxngKeywordSource)
    assert source.base_url == "http://searxng:8080"


def test_enabled_but_unconfigured_yields_no_source():
    assert get_keyword_source(_settings(keyword_enabled=True, dry_run=False)) is None
    assert (
        get_keyword_source(
            _settings(keyword_enabled=True, dry_run=False, serp_base_url="  ")
        )
        is None
    )


def test_dry_run_beats_a_configured_base_url():
    source = get_keyword_source(
        _settings(
            keyword_enabled=True,
            dry_run=True,
            serp_base_url="http://searxng:8080",
        )
    )
    assert isinstance(source, MockKeywordSource)


def test_mock_expand_is_deterministic_and_includes_seed_shaped_rows():
    result = MockKeywordSource().expand("money transfer", locale="en", max_ideas=5)
    assert result.provider == "mock"
    assert result.seed == "money transfer"
    assert len(result.ideas) == 5
    assert result.ideas[0].phrase == "money transfer"
    assert result.ideas[0].source == "seed"
    assert any(idea.source == "variant" for idea in result.ideas)
