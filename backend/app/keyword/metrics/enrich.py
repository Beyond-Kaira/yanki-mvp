"""Merge KeywordMetricRow values into expand idea ``signals``."""

from __future__ import annotations

from collections.abc import Sequence

from app.keyword.base import KeywordIdea
from app.keyword.metrics.base import KeywordMetricRow, KeywordMetricsSource
from app.keyword.normalize import keyword_dedupe_key


def enrich_ideas_with_metrics(
    ideas: Sequence[KeywordIdea],
    source: KeywordMetricsSource,
    *,
    locale: str = "en",
) -> tuple[KeywordIdea, ...]:
    """Attach Ads (or mock) volume fields onto each idea's signals dict.

    On lookup failure the caller should catch and leave ideas unchanged — this
    helper assumes ``source.lookup`` succeeds.
    """
    if not ideas:
        return tuple(ideas)

    phrases = [idea.phrase for idea in ideas]
    rows = source.lookup(phrases, locale=locale)
    by_key = {keyword_dedupe_key(row.phrase): row for row in rows}

    enriched: list[KeywordIdea] = []
    for idea in ideas:
        row = by_key.get(keyword_dedupe_key(idea.phrase))
        if row is None:
            enriched.append(idea)
            continue
        signals = dict(idea.signals or {})
        _apply_metric_row(signals, row)
        enriched.append(KeywordIdea(phrase=idea.phrase, source=idea.source, signals=signals))
    return tuple(enriched)


def _apply_metric_row(signals: dict, row: KeywordMetricRow) -> None:
    signals["volume"] = row.avg_monthly_searches
    signals["volume_estimated"] = bool(row.metrics_estimated)
    signals["metrics_provider"] = row.provider
    if row.competition is not None:
        signals["competition"] = row.competition
    if row.competition_index is not None:
        signals["competition_index"] = row.competition_index
    if row.low_top_of_page_bid_micros is not None:
        signals["low_top_of_page_bid_micros"] = row.low_top_of_page_bid_micros
    if row.high_top_of_page_bid_micros is not None:
        signals["high_top_of_page_bid_micros"] = row.high_top_of_page_bid_micros
