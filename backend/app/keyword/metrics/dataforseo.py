"""DataForSEO Google Ads search volume — volume metrics without a Google Ads account.

Uses ``POST /v3/keywords_data/google_ads/search_volume/live`` (batch up to 1000
keywords). Reuses the same DataForSEO login/password as SERP.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.keyword.metrics.base import KeywordMetricRow, KeywordMetricsUnavailable
from app.keyword.normalize import collapse_keyword_whitespace, keyword_dedupe_key
from app.serp.dataforseo import DEFAULT_TIMEOUT_SECONDS, location_code_for_language

logger = logging.getLogger(__name__)

USER_AGENT = "YankiBot/0.1"
API_URL = "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live"
OK_STATUS = 20000
# Google Ads Keyword Planning rejects some symbols; one bad row fails the whole batch.
_ADS_VOLUME_BLOCKLIST = frozenset("?*$#@!")
_MAX_ADS_KEYWORD_CHARS = 80
_MAX_ADS_KEYWORD_WORDS = 10


def phrase_for_ads_volume_lookup(raw: str) -> str | None:
    """Return a Keyword Planning-safe phrase, or ``None`` when volume lookup must skip."""
    phrase = collapse_keyword_whitespace(raw)
    if not phrase:
        return None
    phrase = phrase.rstrip("?").strip()
    phrase = phrase.replace("$", "")
    if any(ch in phrase for ch in _ADS_VOLUME_BLOCKLIST):
        return None
    if len(phrase) > _MAX_ADS_KEYWORD_CHARS:
        return None
    if len(phrase.split()) > _MAX_ADS_KEYWORD_WORDS:
        return None
    return phrase


class DataForSeoKeywordMetricsSource:
    name = "dataforseo"

    def __init__(
        self,
        login: str,
        password: str,
        *,
        language: str = "en",
        location_code: int | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.login = (login or "").strip()
        self.password = (password or "").strip()
        self.language = (language or "en").strip() or "en"
        self.location_code = location_code_for_language(self.language, override=location_code)
        self.timeout_seconds = timeout_seconds

    def lookup(
        self,
        phrases: list[str],
        *,
        locale: str = "en",
    ) -> list[KeywordMetricRow]:
        # Map each original phrase → API-safe keyword. PAA rows with ``?`` / ``$`` must
        # not be sent or DataForSEO rejects the entire batch.
        originals: list[tuple[str, str]] = []
        seen_original: set[str] = set()
        api_phrases: list[str] = []
        seen_api: set[str] = set()
        for raw in phrases:
            original = collapse_keyword_whitespace(raw)
            orig_key = keyword_dedupe_key(original)
            if not original or orig_key in seen_original:
                continue
            seen_original.add(orig_key)
            api_phrase = phrase_for_ads_volume_lookup(original)
            if not api_phrase:
                continue
            originals.append((original, api_phrase))
            api_key = keyword_dedupe_key(api_phrase)
            if api_key in seen_api:
                continue
            seen_api.add(api_key)
            api_phrases.append(api_phrase)
        if not api_phrases:
            return []
        if not self.login or not self.password:
            raise KeywordMetricsUnavailable("DataForSEO credentials are not configured")

        language = (locale or self.language or "en").strip() or "en"
        location_code = location_code_for_language(language, override=self.location_code or None)
        language_code = language.split("-", 1)[0].lower()

        body = [
            {
                "keywords": api_phrases,
                "location_code": location_code,
                "language_code": language_code,
                "search_partners": False,
            }
        ]

        try:
            timeout = httpx.Timeout(
                connect=10.0,
                read=self.timeout_seconds,
                write=10.0,
                pool=10.0,
            )
            with httpx.Client(
                timeout=timeout,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = client.post(
                    API_URL,
                    json=body,
                    auth=(self.login, self.password),
                )
        except (httpx.HTTPError, OSError) as exc:
            raise KeywordMetricsUnavailable(f"could not reach DataForSEO: {exc}") from exc

        if response.status_code == 401:
            raise KeywordMetricsUnavailable("DataForSEO rejected the credentials")
        if response.status_code >= 400:
            detail = response.text[:500]
            logger.warning(
                "dataforseo search_volume failed status=%s body=%s",
                response.status_code,
                detail,
            )
            raise KeywordMetricsUnavailable(
                f"DataForSEO search_volume HTTP {response.status_code}: {detail}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise KeywordMetricsUnavailable("DataForSEO did not return JSON") from exc
        if not isinstance(payload, dict):
            raise KeywordMetricsUnavailable("DataForSEO returned an unexpected payload")
        api_rows = rows_from_search_volume_payload(payload, provider=self.name)
        by_api_key = {keyword_dedupe_key(row.phrase): row for row in api_rows}
        rows: list[KeywordMetricRow] = []
        seen_out: set[str] = set()
        for original, api_phrase in originals:
            orig_key = keyword_dedupe_key(original)
            if orig_key in seen_out:
                continue
            row = by_api_key.get(keyword_dedupe_key(api_phrase))
            if row is None:
                continue
            seen_out.add(orig_key)
            rows.append(
                KeywordMetricRow(
                    phrase=original,
                    avg_monthly_searches=row.avg_monthly_searches,
                    competition=row.competition,
                    competition_index=row.competition_index,
                    low_top_of_page_bid_micros=row.low_top_of_page_bid_micros,
                    high_top_of_page_bid_micros=row.high_top_of_page_bid_micros,
                    metrics_estimated=row.metrics_estimated,
                    provider=row.provider,
                )
            )
        return rows


def _bid_to_micros(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value) * 1_000_000)
    except (TypeError, ValueError):
        return None


def rows_from_search_volume_payload(
    payload: dict[str, Any],
    *,
    provider: str,
) -> list[KeywordMetricRow]:
    """Parse DataForSEO ``search_volume/live`` JSON into metric rows."""
    if payload.get("status_code") != OK_STATUS:
        message = payload.get("status_message") or "DataForSEO returned an error"
        raise KeywordMetricsUnavailable(str(message))

    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise KeywordMetricsUnavailable("DataForSEO returned no tasks")

    rows: list[KeywordMetricRow] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_status = task.get("status_code")
        if task_status != OK_STATUS:
            msg = task.get("status_message") or "DataForSEO task failed"
            raise KeywordMetricsUnavailable(str(msg))
        results = task.get("result")
        if not isinstance(results, list):
            continue
        for entry in results:
            if not isinstance(entry, dict):
                continue
            phrase = collapse_keyword_whitespace(str(entry.get("keyword") or ""))
            if not phrase:
                continue
            volume = entry.get("search_volume")
            competition = entry.get("competition")
            competition_index = entry.get("competition_index")
            rows.append(
                KeywordMetricRow(
                    phrase=phrase,
                    avg_monthly_searches=int(volume) if volume is not None else None,
                    competition=str(competition).upper() if competition else None,
                    competition_index=(
                        int(competition_index) if competition_index is not None else None
                    ),
                    low_top_of_page_bid_micros=_bid_to_micros(entry.get("low_top_of_page_bid")),
                    high_top_of_page_bid_micros=_bid_to_micros(entry.get("high_top_of_page_bid")),
                    metrics_estimated=False,
                    provider=provider,
                )
            )
    return rows
