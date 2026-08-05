"""Gap analysis, and the outreach source no link-only tool can build.

Two questions, one module.

**The gap** is the classic shopping list: domains that link to competitors but
not to you, ranked. Every suite has it, and it is table stakes.

**The unlinked mentions** are not. Yanki already knows, per analysis, which
third-party pages *cited* a brand in an AI answer (``geo_records.citations``)
and which *named* it in ordinary search results (``serp_checks.matched_url``).
A page that talks about a company without linking to it is the warmest outreach
target that exists — the writer already knows the brand, already published about
it, and simply did not link. A pure link index cannot produce that list because
it only knows about links; this one falls out of data the product collected
while doing something else entirely.

That is differentiator D10, and it costs no vendor call — which matters twice
over, because the licensed index is metered and this is free.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.backlink.normalize import domain_key
from app.db.models import Analysis, GeoRecord, ReferringDomainRollup, SerpCheck


@dataclass(frozen=True)
class GapRow:
    referring_domain: str
    linking_competitors: int
    competitor_domains: tuple[str, ...]
    domain_authority: float | None
    score: float

    def as_dict(self) -> dict:
        return {
            "referring_domain": self.referring_domain,
            "linking_competitors": self.linking_competitors,
            "competitor_domains": list(self.competitor_domains),
            "domain_authority": self.domain_authority,
            "score": round(self.score, 2),
        }


def link_gap(
    session: Session,
    *,
    project_id: uuid.UUID,
    own_domain: str,
    minimum_competitors: int = 1,
    limit: int = 100,
) -> list[GapRow]:
    """Domains linking to ≥N tracked competitors but not to us, best first.

    Ranked by ``competitors × authority`` rather than either alone: a weak
    domain linking to everyone is less valuable than a strong one linking to
    two, and sorting by authority alone would bury the pattern that makes a gap
    list useful — that several rivals independently earned the same link.
    """

    own = domain_key(own_domain) or own_domain

    ours = {
        row[0]
        for row in session.execute(
            select(ReferringDomainRollup.referring_domain).where(
                ReferringDomainRollup.project_id == project_id,
                ReferringDomainRollup.subject_domain == own,
                ReferringDomainRollup.links_count > 0,
            )
        )
    }

    competitor_rows = session.execute(
        select(
            ReferringDomainRollup.referring_domain,
            ReferringDomainRollup.subject_domain,
            ReferringDomainRollup.domain_authority,
        ).where(
            ReferringDomainRollup.project_id == project_id,
            ReferringDomainRollup.subject_kind == "competitor",
            ReferringDomainRollup.links_count > 0,
        )
    )

    grouped: dict[str, dict[str, Any]] = {}
    for referring_domain, subject_domain, authority in competitor_rows:
        if referring_domain in ours or referring_domain == own:
            continue
        bucket = grouped.setdefault(
            referring_domain, {"competitors": set(), "authority": authority}
        )
        bucket["competitors"].add(subject_domain)
        if authority is not None:
            existing = bucket["authority"]
            bucket["authority"] = authority if existing is None else max(existing, authority)

    rows = [
        GapRow(
            referring_domain=referring_domain,
            linking_competitors=len(bucket["competitors"]),
            competitor_domains=tuple(sorted(bucket["competitors"])),
            domain_authority=bucket["authority"],
            score=len(bucket["competitors"]) * ((bucket["authority"] or 0.0) + 1.0),
        )
        for referring_domain, bucket in grouped.items()
        if len(bucket["competitors"]) >= minimum_competitors
    ]
    rows.sort(key=lambda row: (-row.score, row.referring_domain))
    return rows[:limit]


@dataclass(frozen=True)
class UnlinkedMention:
    source_domain: str
    source_url: str
    evidence: str
    seen_via: str

    def as_dict(self) -> dict:
        return {
            "source_domain": self.source_domain,
            "source_url": self.source_url,
            "evidence": self.evidence,
            "seen_via": self.seen_via,
        }


def unlinked_mentions(
    session: Session,
    *,
    project_id: uuid.UUID,
    own_domain: str,
    org_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[UnlinkedMention]:
    """Pages that talked about the brand without linking to it.

    Sources, both already in the database and both free:

    * ``geo_records.citations`` — pages an answer engine cited when discussing
      this brand.
    * ``serp_checks.matched_url`` where ``matched_via == 'text'`` — pages that
      ranked for a brand query by naming it, rather than by being the brand's
      own site.

    Anything whose domain already appears in the referring-domain rollups is
    dropped: it links to us, so it is not an opportunity.

    The analyses scanned are matched by URL host, which is the only join
    available until owned analyses carry ``project_id`` (M4). Stated plainly
    because it bounds what this can see: an analysis run anonymously for the
    same domain is included, and that is intended.
    """

    own = domain_key(own_domain) or own_domain

    already_linking = {
        row[0]
        for row in session.execute(
            select(ReferringDomainRollup.referring_domain).where(
                ReferringDomainRollup.project_id == project_id,
                ReferringDomainRollup.links_count > 0,
            )
        )
    }

    analysis_ids = [
        row[0]
        for row in session.execute(select(Analysis.id, Analysis.url))
        if domain_key(row[1]) == own
    ]
    if not analysis_ids:
        return []

    found: dict[str, UnlinkedMention] = {}

    for citations in session.scalars(
        select(GeoRecord.citations).where(GeoRecord.analysis_id.in_(analysis_ids))
    ):
        for citation in citations or []:
            if not isinstance(citation, dict):
                continue
            url = str(citation.get("url") or "")
            if not url:
                continue
            source = domain_key(citation.get("source_domain") or url)
            if not source or source == own or source in already_linking:
                continue
            found.setdefault(
                source,
                UnlinkedMention(
                    source_domain=source,
                    source_url=url,
                    evidence=str(citation.get("source_title") or "cited in an AI answer"),
                    seen_via="ai_citation",
                ),
            )

    for check in session.execute(
        select(SerpCheck.matched_url, SerpCheck.matched_snippet, SerpCheck.query).where(
            SerpCheck.analysis_id.in_(analysis_ids),
            SerpCheck.matched_via == "text",
            SerpCheck.matched_url.is_not(None),
        )
    ):
        source = domain_key(check.matched_url or "")
        if not source or source == own or source in already_linking:
            continue
        found.setdefault(
            source,
            UnlinkedMention(
                source_domain=source,
                source_url=check.matched_url or "",
                evidence=(check.matched_snippet or f"named in results for “{check.query}”")[:280],
                seen_via="search_result",
            ),
        )

    rows = sorted(found.values(), key=lambda row: row.source_domain)
    return rows[:limit]


def outreach_list(
    session: Session,
    *,
    project_id: uuid.UUID,
    own_domain: str,
    limit: int = 100,
) -> dict[str, Any]:
    """The two opportunity sources in one payload, each labelled with its origin.

    Kept as one call because they answer the same question — "who should we talk
    to?" — and separating them in the API would push the merge into every
    consumer.
    """

    gap = link_gap(session, project_id=project_id, own_domain=own_domain, limit=limit)
    mentions = unlinked_mentions(session, project_id=project_id, own_domain=own_domain, limit=limit)
    return {
        "link_gap": [row.as_dict() for row in gap],
        "unlinked_mentions": [row.as_dict() for row in mentions],
        "provenance": {
            "link_gap": "licensed backlink index, competitor profiles",
            "unlinked_mentions": (
                "Yanki's own citation and SERP evidence — no vendor call, and not "
                "available to link-only tools"
            ),
        },
    }


def anchor_distribution(
    session: Session, *, project_id: uuid.UUID, subject_domain: str
) -> dict[str, Any]:
    """Anchor-class mix, computed on read.

    No rollup table: this is a GROUP BY over a per-plan-capped set, and a
    materialized copy would be one more place for a number to disagree with its
    source.
    """

    from app.db.models import Backlink

    rows = session.execute(
        select(Backlink.anchor_class, func.count())
        .where(
            Backlink.project_id == project_id,
            Backlink.subject_domain == subject_domain,
            Backlink.status == "active",
        )
        .group_by(Backlink.anchor_class)
    )
    counts = {anchor_class: int(count) for anchor_class, count in rows}
    total = sum(counts.values())
    return {
        "total": total,
        "counts": counts,
        "shares": ({k: round(v / total, 4) for k, v in counts.items()} if total else {}),
        # Money-anchor concentration is the one number worth calling out: a high
        # share of commercial anchors is the classic over-optimization pattern.
        "money_anchor_share": (round(counts.get("exact", 0) / total, 4) if total else 0.0),
    }
