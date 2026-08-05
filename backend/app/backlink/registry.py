"""Selecting a backlink index — one function, mirroring ``app/serp/registry.py``.

``None`` is a first-class answer: the module is off, or no vendor is configured
yet (which is the state until operator item **A4** picks one). Callers treat
that as "not measured" rather than "no backlinks", the same discipline ADR-28
established for SERP.

``DRY_RUN`` forces the mock even when a vendor *is* configured. That is
deliberate and stronger than a fallback: the guarantee the test suite depends on
is that a DRY_RUN process cannot reach a paid index by misconfiguration.
"""

from __future__ import annotations

from typing import Any

from app.backlink.base import BacklinkSource
from app.backlink.mock import MockBacklinkSource


def get_backlink_source(settings: Any, *, cycle: int = 0) -> BacklinkSource | None:
    """The configured index, the mock under DRY_RUN, or None when switched off."""

    if not bool(getattr(settings, "backlinks_enabled", False)):
        return None

    if bool(getattr(settings, "dry_run", True)):
        return MockBacklinkSource(cycle=cycle)

    vendor = (getattr(settings, "backlink_vendor", "") or "").strip().lower()
    if not vendor or vendor == "mock":
        return MockBacklinkSource(cycle=cycle)

    # P8.2 lands the first licensed adapter here, as one branch, once the
    # operator answers A4 (vendor + budget). Until then an unrecognised vendor
    # is honestly "not measured" rather than a silent fallback to fixtures that
    # would look like real data.
    return None
