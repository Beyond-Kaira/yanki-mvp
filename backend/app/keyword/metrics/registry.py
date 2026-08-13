"""Pick a keyword metrics source honouring KEYWORD_ADS_ENABLED and credentials."""

from __future__ import annotations

from app.keyword.metrics.base import KeywordMetricsSource
from app.keyword.metrics.google_ads import GoogleAdsKeywordMetricsSource
from app.keyword.metrics.mock import MockKeywordMetricsSource


def get_keyword_metrics_source(settings) -> KeywordMetricsSource | None:
    """Return a metrics source, or ``None`` when Ads enrichment is off / unconfigured."""
    if not getattr(settings, "keyword_ads_enabled", False):
        return None
    if getattr(settings, "dry_run", True):
        return MockKeywordMetricsSource()

    developer_token = (getattr(settings, "google_ads_developer_token", "") or "").strip()
    client_id = (getattr(settings, "google_ads_client_id", "") or "").strip()
    client_secret = (getattr(settings, "google_ads_client_secret", "") or "").strip()
    refresh_token = (getattr(settings, "google_ads_refresh_token", "") or "").strip()
    customer_id = (getattr(settings, "google_ads_customer_id", "") or "").strip()
    login_customer_id = (getattr(settings, "google_ads_login_customer_id", "") or "").strip()
    if not all([developer_token, client_id, client_secret, refresh_token, customer_id]):
        return None

    return GoogleAdsKeywordMetricsSource(
        developer_token=developer_token,
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
        customer_id=customer_id,
        login_customer_id=login_customer_id,
    )
