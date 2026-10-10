"""Pick a keyword metrics source honouring KEYWORD_ADS_ENABLED and credentials."""

from __future__ import annotations

from app.keyword.metrics.base import KeywordMetricsSource
from app.keyword.metrics.dataforseo import DataForSeoKeywordMetricsSource
from app.keyword.metrics.mock import MockKeywordMetricsSource


def _serp_provider(settings) -> str:
    return (getattr(settings, "serp_provider", "") or "searxng").strip().lower()


def get_keyword_metrics_source(settings) -> KeywordMetricsSource | None:
    """Return a metrics source, or ``None`` when volume enrichment is off / unconfigured."""
    if not getattr(settings, "keyword_ads_enabled", False):
        return None
    if getattr(settings, "dry_run", True):
        return MockKeywordMetricsSource()

    if _serp_provider(settings) != "dataforseo":
        return None

    login = (getattr(settings, "dataforseo_login", "") or "").strip()
    password = (getattr(settings, "dataforseo_password", "") or "").strip()
    if not login or not password:
        return None

    location_code = getattr(settings, "dataforseo_location_code", 0) or None
    return DataForSeoKeywordMetricsSource(
        login,
        password,
        language=getattr(settings, "serp_language", "en"),
        location_code=location_code,
        timeout_seconds=float(getattr(settings, "serp_timeout_seconds", 60.0) or 60.0),
    )
