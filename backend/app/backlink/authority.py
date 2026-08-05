"""Yanki Authority — a 0–100 link-strength score that explains itself.

Every suite ships an authority number and none of them will tell you how it is
computed. That opacity is the norm and it is also the opening: this product's
wedge is showing its work, so the formula is published on the methodology page
and every score carries its own decomposition.

Four terms, each answering a question a customer actually asks:

* **Reach** (40) — how many distinct domains link to you at all. The single
  strongest link signal, and the one users understand without explanation.
  Logarithmic, because the 10th referring domain matters far more than the
  500th, and a linear count would let one big customer's chart dwarf every
  other number on the page.
* **Quality** (30) — the authority of those domains, weighted so a handful of
  strong referrers cannot be outvoted by a hundred weak ones.
* **Trust** (20) — the share of links that are follow rather than
  nofollow/UGC/sponsored.
* **Diversity** (10) — how concentrated the profile is. A thousand links from
  three domains is a fragile profile, and a score that ignored that would
  flatter exactly the profiles most at risk.

**Known failure modes, stated rather than hidden.** It inherits the vendor's
domain authority, so it inherits that vendor's biases and gaps. It cannot see
topical relevance — a strong link from an unrelated site scores the same as a
strong link from a peer. It says nothing about whether a link *drives* anything.
And it is not PageRank, is not Google's view, and predicts nothing about
rankings; it describes the profile we can see.

Versioned (:data:`AUTHORITY_VERSION`) and stored with every snapshot, so a
formula change is visible in history rather than silently rewriting the past.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ReferringDomainRollup

AUTHORITY_VERSION = "1.0"

WEIGHT_REACH = 40.0
WEIGHT_QUALITY = 30.0
WEIGHT_TRUST = 20.0
WEIGHT_DIVERSITY = 10.0

# The referring-domain count that scores full marks on reach. Chosen so the
# curve is informative across the range real customers occupy rather than
# saturating immediately.
REACH_SATURATION = 1000.0


@dataclass(frozen=True)
class AuthorityScore:
    value: int
    version: str
    components: dict


def _reach(domain_count: int) -> float:
    if domain_count <= 0:
        return 0.0
    return min(1.0, math.log10(1 + domain_count) / math.log10(1 + REACH_SATURATION))


def _quality(authorities: list[float]) -> float:
    """Weighted mean that leans on the strongest referrers.

    A plain mean lets a hundred near-zero directories drag a genuinely strong
    profile down to nothing; squaring the weights keeps the strong links
    audible without letting one outlier decide the score.
    """

    values = [a for a in authorities if a is not None]
    if not values:
        return 0.0
    weights = [(a / 100.0) ** 2 for a in values]
    total_weight = sum(weights)
    if total_weight <= 0:
        return 0.0
    weighted = sum((a / 100.0) * w for a, w in zip(values, weights, strict=True))
    return min(1.0, weighted / total_weight)


def _trust(follow_links: int, total_links: int) -> float:
    if total_links <= 0:
        return 0.0
    return min(1.0, follow_links / total_links)


def _diversity(links_per_domain: list[int]) -> float:
    """1 − Herfindahl concentration. One domain supplying everything scores 0."""

    total = sum(links_per_domain)
    if total <= 0 or len(links_per_domain) <= 1:
        return 0.0
    shares = [count / total for count in links_per_domain]
    herfindahl = sum(share * share for share in shares)
    # Normalize against the most concentrated possible profile with this many
    # domains, so "diverse" means diverse relative to what was achievable.
    floor = 1.0 / len(links_per_domain)
    return max(0.0, min(1.0, (1.0 - herfindahl) / (1.0 - floor)))


def compute_authority(
    session: Session,
    *,
    project_id: uuid.UUID,
    subject_domain: str,
) -> AuthorityScore:
    """Score one subject's profile from its referring-domain rollups."""

    rows = list(
        session.execute(
            select(
                ReferringDomainRollup.referring_domain,
                ReferringDomainRollup.links_count,
                ReferringDomainRollup.follow_links,
                ReferringDomainRollup.domain_authority,
            ).where(
                ReferringDomainRollup.project_id == project_id,
                ReferringDomainRollup.subject_domain == subject_domain,
                ReferringDomainRollup.links_count > 0,
            )
        )
    )

    domain_count = len(rows)
    total_links = sum(r.links_count for r in rows)
    follow_links = sum(r.follow_links for r in rows)
    authorities = [r.domain_authority or 0.0 for r in rows]
    per_domain = [r.links_count for r in rows]

    reach = _reach(domain_count)
    quality = _quality(authorities)
    trust = _trust(follow_links, total_links)
    diversity = _diversity(per_domain)

    value = (
        reach * WEIGHT_REACH
        + quality * WEIGHT_QUALITY
        + trust * WEIGHT_TRUST
        + diversity * WEIGHT_DIVERSITY
    )

    components = {
        "reach": {
            "weight": WEIGHT_REACH,
            "normalized": round(reach, 4),
            "points": round(reach * WEIGHT_REACH, 2),
            "input": {"referring_domains": domain_count},
            "explains": (
                f"{domain_count} referring domain(s), on a log curve saturating "
                f"at {int(REACH_SATURATION)}"
            ),
        },
        "quality": {
            "weight": WEIGHT_QUALITY,
            "normalized": round(quality, 4),
            "points": round(quality * WEIGHT_QUALITY, 2),
            "input": {
                "mean_domain_authority": round(sum(authorities) / domain_count, 2)
                if domain_count
                else 0.0
            },
            "explains": "authority of referring domains, weighted toward the strongest",
        },
        "trust": {
            "weight": WEIGHT_TRUST,
            "normalized": round(trust, 4),
            "points": round(trust * WEIGHT_TRUST, 2),
            "input": {"follow_links": follow_links, "total_links": total_links},
            "explains": f"{follow_links} of {total_links} link(s) are follow",
        },
        "diversity": {
            "weight": WEIGHT_DIVERSITY,
            "normalized": round(diversity, 4),
            "points": round(diversity * WEIGHT_DIVERSITY, 2),
            "input": {"domains": domain_count},
            "explains": "spread of links across domains (1 − normalized concentration)",
        },
        "caveats": [
            "Inherits the licensed index's domain authority, and therefore its gaps.",
            "Topical relevance is not measured — a strong unrelated link scores "
            "the same as a strong peer link.",
            "Not PageRank, not Google's view, and not a ranking prediction.",
        ],
    }

    return AuthorityScore(
        value=max(0, min(100, round(value))),
        version=AUTHORITY_VERSION,
        components=components,
    )


def velocity(
    session: Session,
    *,
    project_id: uuid.UUID,
    subject_domain: str,
    limit: int = 12,
) -> list[dict]:
    """New/lost per refresh, newest last — read from the import snapshots.

    Deliberately sourced from ``backlink_imports`` rather than counted from link
    rows: the snapshots survive per-plan pruning and a vendor switch, so the
    trend line does not silently rewrite itself when billing changes. Imports
    marked ``retention_boundary`` are excluded, because a cap change is not
    something the web did.
    """

    from app.db.models import BacklinkImport

    rows = list(
        session.execute(
            select(
                BacklinkImport.snapshot_at,
                BacklinkImport.new_in_period,
                BacklinkImport.lost_in_period,
                BacklinkImport.reported_total_backlinks,
                BacklinkImport.measurable,
                BacklinkImport.yanki_authority,
            )
            .where(
                BacklinkImport.project_id == project_id,
                BacklinkImport.subject_domain == subject_domain,
                BacklinkImport.status.in_(("done", "partial")),
                BacklinkImport.retention_boundary.is_(False),
            )
            .order_by(BacklinkImport.created_at.desc())
            .limit(limit)
        )
    )
    return [
        {
            "at": row.snapshot_at.isoformat() if row.snapshot_at else None,
            "new": row.new_in_period,
            "lost": row.lost_in_period,
            "reported_total": row.reported_total_backlinks,
            "measurable": row.measurable,
            "authority": row.yanki_authority,
        }
        for row in reversed(rows)
    ]


def referring_domain_count(session: Session, *, project_id: uuid.UUID, subject_domain: str) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(ReferringDomainRollup)
            .where(
                ReferringDomainRollup.project_id == project_id,
                ReferringDomainRollup.subject_domain == subject_domain,
                ReferringDomainRollup.links_count > 0,
            )
        )
        or 0
    )
