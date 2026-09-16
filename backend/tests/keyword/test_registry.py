"""Which keyword source a given configuration selects.

Live/product path is SearXNG. Mock only under DRY_RUN. Feature dark until
``KEYWORD_ENABLED``.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.keyword.mock import MockKeywordSource
from app.keyword.registry import get_keyword_serp_source, get_keyword_source
from app.keyword.serp_expand import SerpKeywordSource
from app.serp.dataforseo import DataForSeoSource
from app.serp.searxng import SearxngSource


def _settings(**overrides):
    base = {
        "keyword_enabled": False,
        "dry_run": True,
        "serp_provider": "searxng",
        "serp_base_url": "",
        "serp_language": "en",
        "serp_categories": "general",
        "serp_engines": "",
        "serp_safesearch": 0,
        "serp_timeout_seconds": 10.0,
        "serp_max_results": 20,
        "dataforseo_login": "",
        "dataforseo_password": "",
        "dataforseo_location_code": 0,
        "dataforseo_device": "desktop",
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
    assert isinstance(source, SerpKeywordSource)
    assert source.base_url == "http://searxng:8080"


def test_enabled_but_unconfigured_yields_no_source():
    assert get_keyword_source(_settings(keyword_enabled=True, dry_run=False)) is None
    assert (
        get_keyword_source(_settings(keyword_enabled=True, dry_run=False, serp_base_url="  "))
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


def test_enabled_live_dataforseo_builds_keyword_source_from_settings():
    source = get_keyword_source(
        _settings(
            keyword_enabled=True,
            dry_run=False,
            serp_provider="dataforseo",
            dataforseo_login="user@example.com",
            dataforseo_password="secret",
            serp_language="tr",
            dataforseo_location_code=2792,
        )
    )
    assert isinstance(source, SerpKeywordSource)
    assert isinstance(source._serp, DataForSeoSource)
    assert source.name == "dataforseo"
    assert source._serp.login == "user@example.com"
    assert source._serp.language == "tr"
    assert source._serp.location_code == 2792


def test_dataforseo_enabled_but_unconfigured_yields_no_keyword_source():
    assert (
        get_keyword_source(
            _settings(keyword_enabled=True, dry_run=False, serp_provider="dataforseo")
        )
        is None
    )
    assert (
        get_keyword_serp_source(
            _settings(
                keyword_enabled=True,
                dry_run=False,
                serp_provider="dataforseo",
                dataforseo_login="only-login",
            )
        )
        is None
    )


def test_keyword_serp_source_dataforseo_does_not_require_serp_enabled():
    source = get_keyword_serp_source(
        _settings(
            keyword_enabled=True,
            dry_run=False,
            serp_enabled=False,
            serp_provider="dataforseo",
            dataforseo_login="user@example.com",
            dataforseo_password="secret",
        )
    )
    assert isinstance(source, DataForSeoSource)


def test_keyword_serp_source_searxng_still_requires_base_url():
    assert get_keyword_serp_source(_settings(keyword_enabled=True, dry_run=False)) is None
    source = get_keyword_serp_source(
        _settings(
            keyword_enabled=True,
            dry_run=False,
            serp_base_url="http://searxng:8080",
        )
    )
    assert isinstance(source, SearxngSource)


def test_mock_expand_is_deterministic_and_includes_seed_shaped_rows():
    result = MockKeywordSource().expand("money transfer", locale="en", max_ideas=5)
    assert result.provider == "mock"
    assert result.seed == "money transfer"
    assert len(result.ideas) == 5
    assert result.ideas[0].phrase == "money transfer"
    assert result.ideas[0].source == "seed"
    sources = [idea.source for idea in result.ideas]
    assert "mock" in sources
    assert "variant" in sources
    assert sources.index("mock") < sources.index("variant")
