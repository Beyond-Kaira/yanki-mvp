"""Deterministic metrics for DRY_RUN / CI — never used as the live product path."""

from __future__ import annotations

from app.keyword.metrics.base import KeywordMetricRow
from app.keyword.normalize import collapse_keyword_whitespace, keyword_dedupe_key


class MockKeywordMetricsSource:
    name = "mock"

    def lookup(
        self,
        phrases: list[str],
        *,
        locale: str = "en",
    ) -> list[KeywordMetricRow]:
        rows: list[KeywordMetricRow] = []
        seen: set[str] = set()
        for raw in phrases:
            phrase = collapse_keyword_whitespace(raw)
            key = keyword_dedupe_key(phrase)
            if not phrase or key in seen:
                continue
            seen.add(key)
            # Stable pseudo-volume from phrase length so tests can assert shape.
            volume = 100 + (len(key) * 17) % 900
            rows.append(
                KeywordMetricRow(
                    phrase=phrase,
                    avg_monthly_searches=volume,
                    competition="MEDIUM",
                    competition_index=50,
                    metrics_estimated=False,
                    provider=self.name,
                )
            )
        return rows
