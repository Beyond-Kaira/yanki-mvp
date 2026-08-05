"""A deterministic backlink index, so the whole module runs at $0 under DRY_RUN.

The hard part of mocking this seam is **time**. Every interesting behaviour in
Phase 8 is a difference between two refreshes: new links, lost links, a regained
link, velocity, a vendor that goes partial. A mock that returns the same page
forever can exercise none of it, and a mock that uses the wall clock makes the
tests it enables non-reproducible.

So the mock is a pure function of ``(subject_domain, cycle)``. The cycle is an
explicit integer the caller advances — the importer passes the count of prior
imports for that subject — which means a test can say "run cycle 0, then cycle
2" and get exactly the profile evolution it wants to assert on, every run, on
every machine. There is no clock and no RNG anywhere in this file; the seeded
variation comes from a hash of the domain, so two different domains have
genuinely different profiles while each one is reproducible.

The evolution schedule below is designed so a single fixture exercises every
delta path the engine has:

* cycle 0 — a baseline profile.
* cycle 1 — two links added (``new``), one dropped (a ``lost`` candidate).
* cycle 2 — the dropped link returns (``regained``, not ``new``), one anchor
  changes (``changed``), and one link stays gone (a real ``lost``).
* cycle 3 — the vendor truncates (``coverage_status='partial'``): the import is
  not measurable and must mint **zero** losses despite a much shorter page.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.backlink.base import BacklinkPage, BacklinkRow
from app.backlink.pricing import page_cost

NAME = "mock"

# A fixed epoch, not "now". Every date the mock produces is derived from it, so
# a stored fixture stays valid a year from now and two runs on different days
# produce identical rows.
EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def _seed(domain: str) -> int:
    """A stable per-domain integer. hashlib, not hash(), which is salted per process."""

    digest = hashlib.sha256(domain.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def _referrers(domain: str) -> list[tuple[str, float, str, str | None]]:
    """(referring domain, authority, tld, ip) — deterministic from the subject.

    The last three entries are deliberately unpleasant: a link-farm cluster
    sharing a /24, a spammy TLD, and a zero-authority domain — so the toxicity
    heuristics have something real to find without a special "toxic" fixture.
    """

    seed = _seed(domain)
    return [
        (f"news{seed % 7}.example", 78.0, "example", "203.0.113.10"),
        (f"blog{seed % 11}.example", 54.0, "example", "203.0.113.11"),
        ("directory.example", 31.0, "example", "198.51.100.7"),
        ("partner.example", 62.0, "example", "198.51.100.8"),
        ("forum.example", 22.0, "example", "192.0.2.44"),
        # link-farm shape: three domains, one /24, no authority
        ("farm-a.example", 2.0, "example", "192.0.2.1"),
        ("farm-b.example", 1.0, "example", "192.0.2.2"),
        ("cheap-seo.top", 0.0, "top", "192.0.2.3"),
    ]


def _base_rows(domain: str) -> list[BacklinkRow]:
    rows: list[BacklinkRow] = []
    for index, (referrer, authority, tld, ip) in enumerate(_referrers(domain)):
        rows.append(
            BacklinkRow(
                source_url=f"https://{referrer}/post-{index}",
                source_domain=referrer,
                target_url=f"https://{domain}/",
                anchor=_anchor_for(index, domain),
                attrs=("nofollow",) if index % 4 == 3 else (),
                is_image_link=index == 2,
                vendor_first_seen=EPOCH + timedelta(days=index * 3),
                vendor_last_seen=EPOCH + timedelta(days=90),
                source_domain_authority=authority,
                source_page_authority=max(0.0, authority - 10.0),
                source_ip=ip,
                source_tld=tld,
                vendor_spam_score=0.0 if authority > 20 else 82.0,
            )
        )
    return rows


def _anchor_for(index: int, domain: str) -> str:
    label = domain.split(".")[0]
    return [
        label,
        f"{label} review",
        "",
        "click here",
        f"https://{domain}/",
        "best cheap widgets online",
        "buy widgets cheap",
        "widgets discount",
    ][index % 8]


class MockBacklinkSource:
    """The $0 index. Deterministic in ``(subject_domain, cycle)``."""

    name = NAME

    def __init__(self, cycle: int = 0) -> None:
        self.cycle = max(0, int(cycle))

    def fetch_backlinks(self, subject_domain: str, *, cursor: str | None = None) -> BacklinkPage:
        rows = _base_rows(subject_domain)
        cycle = self.cycle
        coverage = "complete"

        if cycle >= 1:
            # Two born, one dropped.
            rows.append(
                BacklinkRow(
                    source_url=f"https://fresh-a.example/{subject_domain}",
                    source_domain="fresh-a.example",
                    target_url=f"https://{subject_domain}/",
                    anchor=subject_domain.split(".")[0],
                    vendor_first_seen=EPOCH + timedelta(days=120),
                    vendor_last_seen=EPOCH + timedelta(days=150),
                    source_domain_authority=66.0,
                    source_ip="203.0.113.20",
                    source_tld="example",
                )
            )
            rows.append(
                BacklinkRow(
                    source_url=f"https://fresh-b.example/{subject_domain}",
                    source_domain="fresh-b.example",
                    target_url=f"https://{subject_domain}/",
                    anchor="great tool",
                    vendor_first_seen=EPOCH + timedelta(days=121),
                    vendor_last_seen=EPOCH + timedelta(days=150),
                    source_domain_authority=41.0,
                    source_ip="203.0.113.21",
                    source_tld="example",
                )
            )
            rows = [r for r in rows if r.source_domain != "forum.example"]

        if cycle >= 2:
            # The dropped one returns — a `regained`, never a second birth —
            # while a different link stays gone, and one anchor is rewritten.
            rows.append(
                BacklinkRow(
                    source_url="https://forum.example/post-4",
                    source_domain="forum.example",
                    target_url=f"https://{subject_domain}/",
                    anchor=f"https://{subject_domain}/",
                    vendor_first_seen=EPOCH + timedelta(days=12),
                    vendor_last_seen=EPOCH + timedelta(days=180),
                    source_domain_authority=22.0,
                    source_ip="192.0.2.44",
                    source_tld="example",
                )
            )
            rows = [r for r in rows if r.source_domain != "directory.example"]
            rows = [
                (
                    r
                    if r.source_domain != "partner.example"
                    else BacklinkRow(**{**r.__dict__, "anchor": "official partner page"})
                )
                for r in rows
            ]

        if cycle >= 3:
            # The vendor truncates. Far fewer rows, and it says so — the
            # importer must record what it saw and mint no losses at all.
            rows = rows[:2]
            coverage = "partial"

        cost = page_cost(self.name, len(rows))
        return BacklinkPage(
            subject_domain=subject_domain,
            rows=tuple(rows),
            next_cursor=None,
            # The claimed grand total tracks the profile, not the page — which
            # is what lets velocity stay honest when a plan cap truncates rows.
            reported_total_backlinks=len(rows) if coverage == "complete" else 42,
            reported_total_referring_domains=(
                len({r.source_domain for r in rows}) if coverage == "complete" else 30
            ),
            coverage_status=coverage,  # type: ignore[arg-type]
            cost=cost,
            fetched_at=EPOCH + timedelta(days=150 + cycle),
        )

    def price_estimate(self, subject_domain: str) -> Decimal:
        return page_cost(self.name, 10_000)
