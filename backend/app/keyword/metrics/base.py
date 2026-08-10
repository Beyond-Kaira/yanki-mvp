"""Keyword metrics providers (volume / competition / CPC) — separate from discovery.

Discovery stays SearXNG. This seam is for Google Ads Keyword Planning (and later
wholesale). See ``docs/keyword-preview-oss.md`` Ads volume metrics policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class KeywordMetricRow:
    """Ground-truth-ish metrics for one phrase (locale/geo applied by the source)."""

    phrase: str
    avg_monthly_searches: int | None
    competition: str | None = None  # LOW / MEDIUM / HIGH when Ads provides it
    competition_index: int | None = None
    low_top_of_page_bid_micros: int | None = None
    high_top_of_page_bid_micros: int | None = None
    metrics_estimated: bool = False
    provider: str = ""


@runtime_checkable
class KeywordMetricsSource(Protocol):
    name: str

    def lookup(
        self,
        phrases: list[str],
        *,
        locale: str = "en",
    ) -> list[KeywordMetricRow]:
        """Return metrics for ``phrases`` (order may differ; missing phrases omitted)."""
        ...
