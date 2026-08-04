"""Composite GEO score from measured audit fields (0–100).

The score is derived only from deterministic / controlled fields:

* ``mentioned`` (0|1)
* ``mention_context`` → position weight
* ``citation_metrics`` → citation weight
* ``sentiment`` → sentiment weight (treated as neutral when reliability is low)

``visibility_gaps`` / gap counts do not enter the score.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

POSITION_WEIGHTS: dict[str, float] = {
    "primary_recommendation": 1.0,
    "secondary_recommendation": 0.7,
    "comparison_candidate": 0.7,
    "alternative_option": 0.4,
    "competitor_only": 0.4,
    "not_mentioned": 0.0,
}

SENTIMENT_WEIGHTS: dict[str, float] = {
    "positive": 1.0,
    "neutral": 0.9,
    "negative": 0.5,
}

RELIABILITY_SENTIMENT_FLOOR = 0.5
NEUTRAL_SENTIMENT_WEIGHT = 0.9


def mention_rate(footprints: int, total: int) -> float:
    """Legacy helper: ``footprints / total`` in 0–1. Safe when total is 0."""
    if total <= 0:
        return 0.0
    return footprints / total


def position_weight(mention_context: str | None) -> float:
    if not mention_context:
        return 0.0
    return POSITION_WEIGHTS.get(mention_context, 0.0)


def citation_weight(
    *,
    mentioned: bool,
    target_brand_cited: bool,
    owned_media_cited: bool,
) -> float:
    if not mentioned:
        return 0.0
    if target_brand_cited and owned_media_cited:
        return 1.0
    if target_brand_cited:
        return 0.85
    return 0.6


def sentiment_weight(
    sentiment: str | None,
    *,
    reliability_score: float | None = None,
) -> float:
    if reliability_score is not None and reliability_score < RELIABILITY_SENTIMENT_FLOOR:
        return NEUTRAL_SENTIMENT_WEIGHT
    key = (sentiment or "neutral").lower()
    return SENTIMENT_WEIGHTS.get(key, NEUTRAL_SENTIMENT_WEIGHT)


def per_prompt_score(
    record: Mapping[str, Any],
    *,
    reliability_score: float | None = None,
) -> float:
    """One prompt's contribution in 0–1 before averaging."""
    mentioned = bool(record.get("mentioned"))
    if not mentioned:
        return 0.0

    metrics = record.get("citation_metrics") or {}
    return (
        1.0
        * position_weight(record.get("mention_context"))
        * citation_weight(
            mentioned=True,
            target_brand_cited=bool(metrics.get("target_brand_cited")),
            owned_media_cited=bool(metrics.get("owned_media_cited")),
        )
        * sentiment_weight(
            record.get("sentiment"),
            reliability_score=reliability_score,
        )
    )


def geo_score(
    records: Sequence[Mapping[str, Any]],
    *,
    reliability_score: float | None = None,
) -> float:
    """Mean per-prompt score × 100, clamped to 0–100. Empty → 0.0."""
    if not records:
        return 0.0
    total = sum(per_prompt_score(record, reliability_score=reliability_score) for record in records)
    return max(0.0, min(100.0, (total / len(records)) * 100.0))
