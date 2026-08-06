"""Estimated demand / difficulty proxies for keyword-expand preview rows.

These are **not** monthly search volume or Semrush KD%. UI and API must label
them Estimated. Real metrics later plug in via the same ``signals`` keys where
possible (swap provider, keep field names stable where noted in
``docs/keyword-preview-oss.md``).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.keyword.intent import classify_keyword_search_intent
from app.keyword.normalize import collapse_keyword_whitespace
from app.serp.base import SerpPage

# Provenance → higher score means "more likely someone actually searches this"
# in the absence of volume. Suggestions from the engine beat local templates.
_ESTIMATED_DEMAND_BY_DISCOVERY_SOURCE: dict[str, int] = {
    "suggestion": 78,
    "paa": 72,
    "related": 58,
    "seed": 52,
    "variant": 42,
    "mock": 36,
}

# Host fragments that usually mean "hard page one" when they dominate a SERP.
_HARD_SERP_HOST_FRAGMENTS = (
    "wikipedia.org",
    "amazon.",
    "youtube.com",
    "youtu.be",
    "facebook.com",
    "linkedin.com",
    "instagram.com",
    "nytimes.com",
    "forbes.com",
    "bloomberg.com",
    "hubspot.com",
    "g2.com",
    "capterra.com",
    "trustpilot.com",
    "reddit.com",
)


def estimated_demand_score_for_discovery_source(discovery_source: str) -> int:
    """0–100 estimated demand from how the idea was found (not search volume)."""
    base = _ESTIMATED_DEMAND_BY_DISCOVERY_SOURCE.get(discovery_source, 45)
    return max(0, min(100, base))


def estimated_difficulty_score_from_seed_serp(page: SerpPage | None) -> int | None:
    """0–100 estimated difficulty from the **seed** SERP's top results.

    One SearXNG round-trip is shared across the expand, so this is a
    topic-level hint (``difficulty_basis: seed_serp``), not per-keyword KD.
    """
    if page is None or not page.results:
        return None
    sample = page.results[:10]
    hard_hits = 0
    for result in sample:
        host = urlparse(result.url).netloc.lower()
        if any(fragment in host for fragment in _HARD_SERP_HOST_FRAGMENTS):
            hard_hits += 1
    ratio = hard_hits / len(sample)
    # Empty-of-giants SERPs sit near 35; giant-heavy ones near 95.
    return max(0, min(100, int(35 + ratio * 60)))


def build_estimated_keyword_idea_signals(
    *,
    phrase: str,
    discovery_source: str,
    seed_serp_page: SerpPage | None = None,
) -> dict[str, Any]:
    """Signals dict attached to each :class:`~app.keyword.base.KeywordIdea`."""
    cleaned = collapse_keyword_whitespace(phrase)
    difficulty = estimated_difficulty_score_from_seed_serp(seed_serp_page)
    signals: dict[str, Any] = {
        "intent": classify_keyword_search_intent(cleaned),
        "estimated_demand_score": estimated_demand_score_for_discovery_source(discovery_source),
        "volume_estimated": True,
        "difficulty_estimated": True,
    }
    if difficulty is None:
        signals["estimated_difficulty_score"] = None
        signals["difficulty_basis"] = "none"
    else:
        signals["estimated_difficulty_score"] = difficulty
        signals["difficulty_basis"] = "seed_serp"
    return signals
