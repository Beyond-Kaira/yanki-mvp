"""Keyword metrics providers (volume / competition / CPC) — separate from discovery.

Discovery stays on the SERP provider. Volume can come from direct Google Ads API
or DataForSEO Keywords Data (Google Ads search volume proxy). See
``docs/keyword-preview-oss.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class KeywordMetricsUnavailable(Exception):
    """Metrics could not be fetched (auth, quota, or transport)."""


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
