"""Google Ads Keyword Planning metrics via REST (GenerateKeywordHistoricalMetrics)."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.keyword.metrics.base import KeywordMetricRow
from app.keyword.metrics.locale_map import ads_language_and_geo_for_locale
from app.keyword.normalize import collapse_keyword_whitespace, keyword_dedupe_key

logger = logging.getLogger(__name__)

_ADS_SCOPE = "https://www.googleapis.com/auth/adwords"
# Pin a supported REST version; bump deliberately when Google sunsets.
# v20 is deprecated (UNSUPPORTED_VERSION); prefer a current GA pin.
_ADS_API_VERSION = "v22"


class GoogleAdsMetricsUnavailable(Exception):
    """Ads metrics could not be fetched (auth, quota, or transport)."""


class GoogleAdsKeywordMetricsSource:
    name = "google_ads"

    def __init__(
        self,
        *,
        developer_token: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        customer_id: str,
        login_customer_id: str = "",
        timeout_seconds: float = 30.0,
        api_version: str = _ADS_API_VERSION,
    ) -> None:
        self._developer_token = developer_token.strip()
        self._client_id = client_id.strip()
        self._client_secret = client_secret.strip()
        self._refresh_token = refresh_token.strip()
        self._customer_id = _digits_only(customer_id)
        self._login_customer_id = _digits_only(login_customer_id) or self._customer_id
        self._timeout = timeout_seconds
        self._api_version = api_version.strip() or _ADS_API_VERSION
        self._access_token_cache: str | None = None
        self._access_token_expires_at = 0.0

    def lookup(
        self,
        phrases: list[str],
        *,
        locale: str = "en",
    ) -> list[KeywordMetricRow]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in phrases:
            phrase = collapse_keyword_whitespace(raw)
            key = keyword_dedupe_key(phrase)
            if not phrase or key in seen:
                continue
            seen.add(key)
            cleaned.append(phrase)
        if not cleaned:
            return []

        language, geo = ads_language_and_geo_for_locale(locale)
        access_token = self._access_token()
        url = (
            f"https://googleads.googleapis.com/{self._api_version}/"
            f"customers/{self._customer_id}:generateKeywordHistoricalMetrics"
        )
        headers = {
            "Authorization": f"Bearer {access_token}",
            "developer-token": self._developer_token,
            "login-customer-id": self._login_customer_id,
            "Content-Type": "application/json",
        }
        body = {
            "keywords": cleaned,
            "language": language,
            "geoTargetConstants": [geo],
            "keywordPlanNetwork": "GOOGLE_SEARCH",
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise GoogleAdsMetricsUnavailable(str(exc) or "ads transport error") from exc

        if response.status_code >= 400:
            detail = response.text[:500]
            logger.warning(
                "google_ads historical metrics failed status=%s body=%s",
                response.status_code,
                detail,
            )
            raise GoogleAdsMetricsUnavailable(
                f"google ads metrics HTTP {response.status_code}: {detail}"
            )

        payload = response.json()
        return _rows_from_historical_metrics_response(payload, provider=self.name)

    def _access_token(self) -> str:
        now = time.time()
        if self._access_token_cache and now < self._access_token_expires_at - 60:
            return self._access_token_cache
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "refresh_token": self._refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
        except httpx.HTTPError as exc:
            raise GoogleAdsMetricsUnavailable(
                str(exc) or "google ads oauth transport error"
            ) from exc
        if response.status_code >= 400:
            raise GoogleAdsMetricsUnavailable(
                f"google ads oauth refresh HTTP {response.status_code}: {response.text[:300]}"
            )
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise GoogleAdsMetricsUnavailable("google ads access token empty after refresh")
        expires_in = int(payload.get("expires_in") or 3600)
        self._access_token_cache = str(token)
        self._access_token_expires_at = now + expires_in
        return self._access_token_cache


def _digits_only(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _rows_from_historical_metrics_response(
    payload: dict[str, Any],
    *,
    provider: str,
) -> list[KeywordMetricRow]:
    rows: list[KeywordMetricRow] = []
    for entry in payload.get("results") or []:
        if not isinstance(entry, dict):
            continue
        text = collapse_keyword_whitespace(str(entry.get("text") or ""))
        if not text:
            continue
        metrics = entry.get("keywordMetrics") or {}
        if not isinstance(metrics, dict):
            metrics = {}
        avg = metrics.get("avgMonthlySearches")
        competition = metrics.get("competition")
        competition_index = metrics.get("competitionIndex")
        low_bid = metrics.get("lowTopOfPageBidMicros")
        high_bid = metrics.get("highTopOfPageBidMicros")
        rows.append(
            KeywordMetricRow(
                phrase=text,
                avg_monthly_searches=int(avg) if avg is not None else None,
                competition=str(competition) if competition else None,
                competition_index=int(competition_index)
                if competition_index is not None
                else None,
                low_top_of_page_bid_micros=int(low_bid) if low_bid is not None else None,
                high_top_of_page_bid_micros=int(high_bid) if high_bid is not None else None,
                metrics_estimated=False,
                provider=provider,
            )
        )
    return rows
