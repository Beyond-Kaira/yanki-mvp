"""DataForSEO Backlinks API adapter (mod-10).

Separate billing from SERP/Keywords. Enabled when ``BACKLINK_VENDOR=dataforseo``
and ``BACKLINKS_ENABLED=1``. Live API mapping lands when operator credentials
and endpoint choice are pinned (see ``docs/dataforseo-touchpoint-map.md``).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.backlink.base import BacklinkPage, BacklinkSourceUnavailable

NAME = "dataforseo"


class DataForSeoBacklinkSource:
    """Placeholder seam — refuses until the licensed fetch path is wired."""

    name = NAME

    def __init__(self, settings: Any) -> None:
        self._settings = settings

    def fetch_backlinks(self, subject_domain: str, *, cursor: str | None = None) -> BacklinkPage:
        raise BacklinkSourceUnavailable(
            "DataForSEO backlinks adapter is not configured for live fetch yet (mod-10)"
        )

    def price_estimate(self, subject_domain: str) -> Decimal:
        raise BacklinkSourceUnavailable(
            "DataForSEO backlinks adapter is not configured for live fetch yet (mod-10)"
        )


def as_backlink_source(settings: Any) -> DataForSeoBacklinkSource:
    return DataForSeoBacklinkSource(settings)
