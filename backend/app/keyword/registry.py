"""Pick the keyword source, honouring ``KEYWORD_ENABLED`` and ``DRY_RUN``.

Mirrors ``app/serp/registry.py``. Returns ``None`` when the feature is off or
the configured SERP provider is enabled-but-unconfigured — better than a source
that fails on every expand. Provider selection follows ``SERP_PROVIDER`` (SearXNG
or DataForSEO); mock only when ``DRY_RUN`` is on.
"""

from __future__ import annotations

from app.keyword.base import KeywordSource
from app.keyword.mock import MockKeywordSource
from app.keyword.serp_expand import SerpKeywordSource
from app.serp.base import SerpSource
from app.serp.mock import MockSerpSource
from app.serp.registry import build_configured_serp_source


def get_keyword_source(settings) -> KeywordSource | None:
    """The source for keyword expand, or ``None`` when the feature is off."""
    if not getattr(settings, "keyword_enabled", False):
        return None
    if getattr(settings, "dry_run", True):
        return MockKeywordSource()
    serp = build_configured_serp_source(settings)
    if serp is None:
        return None
    return SerpKeywordSource(serp)


def get_keyword_serp_source(settings) -> SerpSource | None:
    """SERP reader for rank-check — same KEYWORD_ENABLED / DRY_RUN gates as expand.

    Does not require ``SERP_ENABLED``: keyword preview opts in via
    ``KEYWORD_ENABLED`` plus a configured ``SERP_PROVIDER`` (and credentials or
    ``SERP_BASE_URL`` for SearXNG).
    """
    if not getattr(settings, "keyword_enabled", False):
        return None
    if getattr(settings, "dry_run", True):
        return MockSerpSource()
    return build_configured_serp_source(settings)
