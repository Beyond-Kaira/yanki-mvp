"""Pinned prices for backlink index calls. Cost is computed, never echoed.

The anti-pattern this module exists to avoid is two files away and cost this
project a week of blind spending: ``providers/openrouter.py`` reads the vendor's
own ``usage.cost`` and falls back to ``0.0`` when it is absent, so a response
shape change silently became "this call was free" (ADR-34, tech-debt #58).

Here, price is a property of *our* table keyed by vendor and unit. A vendor we
have no price for cannot be billed silently — :func:`page_cost` raises, the
importer degrades the refresh, and nothing paid goes unrecorded.

Every number below is **UNVERIFIED** until a contract exists (operator item
**A4** picks the vendor and budget). They are deliberately set high: an
over-estimate makes a quota trip early, which is annoying; an under-estimate
makes it trip late, which is expensive.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.backlink.base import BacklinkSourceUnavailable

# Dollars per 1,000 link rows returned, per vendor. The mock is genuinely free
# and says so, which is what makes the DRY_RUN suite's "$0" assertion mean
# something rather than merely reflecting an absent field.
PRICE_PER_1K_ROWS: dict[str, Decimal] = {
    "mock": Decimal("0"),
    # Wholesale-API-class placeholder, the plan's default candidate shape.
    # Replace with the contracted rate when A4 is answered.
    "dataforseo": Decimal("0.60"),
}

# A floor per request, because most vendors bill per call as well as per row.
MINIMUM_REQUEST_COST: dict[str, Decimal] = {
    "mock": Decimal("0"),
    "dataforseo": Decimal("0.003"),
}

# Worst-case rows assumed for a full pull when estimating BEFORE the first call.
# Used only for the up-front quota reservation, where over-estimating is the
# safe direction.
ESTIMATE_ROWS = 10_000

_CENTS = Decimal("0.000001")


def page_cost(vendor: str, row_count: int) -> Decimal:
    """What one page of ``row_count`` rows costs, per the pinned table.

    Raises :class:`BacklinkSourceUnavailable` for an unknown vendor rather than
    returning zero. A call we cannot price is a call we cannot cap, and the
    honest response is to refuse it — not to record it as free.
    """

    if vendor not in PRICE_PER_1K_ROWS:
        raise BacklinkSourceUnavailable(
            f"no pinned price for backlink vendor {vendor!r}; refusing to bill an "
            "unpriceable call (see app/backlink/pricing.py)"
        )

    per_1k = PRICE_PER_1K_ROWS[vendor]
    floor = MINIMUM_REQUEST_COST.get(vendor, Decimal("0"))
    rows = Decimal(max(0, int(row_count)))
    cost = (rows / Decimal(1000)) * per_1k
    return max(cost, floor).quantize(_CENTS, rounding=ROUND_HALF_UP)


def full_pull_estimate(vendor: str, *, rows: int = ESTIMATE_ROWS) -> Decimal:
    """Worst-case cost of pulling a whole profile, for the quota reservation."""

    return page_cost(vendor, rows)
