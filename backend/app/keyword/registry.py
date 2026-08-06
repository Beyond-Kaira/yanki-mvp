"""Pick the keyword source, honouring ``KEYWORD_ENABLED`` and ``DRY_RUN``.

Mirrors ``app/serp/registry.py``. Returns ``None`` when the feature is off or
SearXNG is enabled-but-unconfigured — better than a source that fails on every
expand. Live/default product path is SearXNG; mock only when ``DRY_RUN`` is on.
"""

from __future__ import annotations

from app.keyword.base import KeywordSource
from app.keyword.mock import MockKeywordSource
from app.keyword.searxng_expand import SearxngKeywordSource
from app.serp.searxng import SearxngSource


def get_keyword_source(settings) -> KeywordSource | None:
    """The source for keyword expand, or ``None`` when the feature is off."""
    if not getattr(settings, "keyword_enabled", False):
        return None
    if getattr(settings, "dry_run", True):
        return MockKeywordSource()
    base_url = (getattr(settings, "serp_base_url", "") or "").strip()
    if not base_url:
        return None
    serp = SearxngSource(
        base_url,
        language=getattr(settings, "serp_language", "en"),
        categories=getattr(settings, "serp_categories", "general"),
        engines=getattr(settings, "serp_engines", ""),
        safesearch=getattr(settings, "serp_safesearch", 0),
        timeout_seconds=getattr(settings, "serp_timeout_seconds", 10.0),
        max_results=getattr(settings, "serp_max_results", 20),
    )
    return SearxngKeywordSource(serp)
