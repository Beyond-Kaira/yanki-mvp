"""The interface every backlink index implements.

Modelled on ``app/serp/base.py`` rather than ``app/providers/base.py``, because
the SERP seam already solved this module's central problem: **a page must carry
the evidence needed to trust it.** A licensed index answers ``200 OK`` with a
truncated set when a cursor is exhausted, a quota runs out, or a plan cap bites.
Reading that short page as "these links are gone" would manufacture mass link
loss out of a failed measurement — and "you lost 4,000 backlinks" is the single
most alarming false claim this product could make.

So: :attr:`BacklinkPage.measurable` refuses to let an incomplete page support an
*absence* claim. An incomplete page may still ADD links it saw; it may never
SUBTRACT. Absence from a truncated set is not evidence of absence.

Two deliberate deviations from the SERP seam:

* **Cost is authoritative and computed here, never echoed from the vendor.** The
  anti-pattern is in ``providers/openrouter.py``, which reads the vendor's own
  ``usage.cost`` and *falls back to zero when absent* — that is how the measured
  GEO path recorded $0 for a week (ADR-34, tech-debt #58). A page this seam
  cannot price raises instead, because an unpriced call is an uncapped call.
* **``price_estimate`` exists** so the quota gate can bound spend BEFORE the
  request, not discover it afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable


class BacklinkSourceUnavailable(Exception):
    """The index was unreachable, or answered unusably — including unpriceably.

    Always caught by the importer: the refresh degrades to a non-measurable
    import (``coverage_status='failed'``) and mints no losses. Never fails the
    job, never fabricates an empty profile. Same contract as ``SerpUnavailable``
    and the same reasoning as ADR-28.
    """


LinkAttr = Literal["nofollow", "ugc", "sponsored"]
CoverageStatus = Literal["complete", "partial", "empty", "failed"]


@dataclass(frozen=True)
class BacklinkRow:
    """One link as the vendor claims to see it this cycle. A raw observation.

    ``vendor_first_seen`` is the field that makes honest deltas possible. Link
    *birth* is classified from it, never from "this row is absent from our
    table" — because our table is capped per plan, so a plan upgrade would
    otherwise re-mint tens of thousands of false "new backlink!" events on the
    happiest day of a customer's month.
    """

    source_url: str
    source_domain: str
    target_url: str
    anchor: str = ""
    attrs: tuple[LinkAttr, ...] = ()
    is_image_link: bool = False
    vendor_first_seen: datetime | None = None
    vendor_last_seen: datetime | None = None
    source_domain_authority: float | None = None
    source_page_authority: float | None = None
    # Enables /24 subnet clustering in the toxicity heuristics. None means the
    # vendor did not say — which is different from "not clustered".
    source_ip: str | None = None
    source_tld: str = ""
    vendor_spam_score: float | None = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class BacklinkPage:
    """One vendor response page for one subject domain (own or a competitor's)."""

    subject_domain: str
    rows: tuple[BacklinkRow, ...] = ()
    next_cursor: str | None = None
    # The vendor's claimed grand totals, which are NOT the same as len(rows):
    # they describe the whole profile, while rows describe this page. Velocity
    # is computed from these so a per-plan row cap never distorts the headline.
    reported_total_backlinks: int | None = None
    reported_total_referring_domains: int | None = None
    coverage_status: CoverageStatus = "complete"
    # Authoritative, from the pinned price table — never the vendor's echo.
    cost: Decimal = Decimal("0")
    fetched_at: datetime | None = None

    @property
    def measurable(self) -> bool:
        """May this page support an *absence* claim?

        Only if it is whole and clean. This is necessary but not sufficient —
        the whole-import gate in ``delta.py`` additionally compares against the
        previous import, because a vendor can return a complete-looking page
        that is a fraction of last week's profile.
        """

        return self.coverage_status == "complete"


@runtime_checkable
class BacklinkSource(Protocol):
    """A licensed backlink index behind one adapter."""

    name: str

    def fetch_backlinks(
        self, subject_domain: str, *, cursor: str | None = None
    ) -> BacklinkPage: ...

    def price_estimate(self, subject_domain: str) -> Decimal:
        """Worst-case cost of a full pull, for the up-front quota reservation."""
        ...
