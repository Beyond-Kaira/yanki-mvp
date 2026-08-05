"""Toxicity assessment — advisory, decomposable, and deliberately under-confident.

The category's standard move is a red "TOXIC 87/100" badge with nothing behind
it, and it is a credibility trap: the label is a guess about what a search engine
thinks, presented as a measurement. Acting on a wrong one costs a customer real
links. So three rules govern this module:

1. **Every flag decomposes.** A score is never shown without the reasons that
   produced it, each with its own weight and the evidence it fired on. A band
   with no reasons is a bug, not a quiet score.
2. **The wording is advisory and says who decides.** Nothing here claims a link
   *is* harmful or that Google penalizes it — only that it carries patterns
   commonly associated with manipulation, and that a human should look.
3. **Nothing is ever auto-disavowed.** The export is a file a person reviews and
   submits; this module does not act.

Scored at domain grain rather than per link, because every signal available —
authority, TLD, subnet clustering, anchor pattern — is a property of the
referring *domain*. Recomputed with each import, so it is a pure function of the
current profile rather than a value that drifts.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Backlink, ReferringDomainRollup

TOXICITY_VERSION = "1.0"

# TLDs repeatedly over-represented in link-selling networks. A weak signal on
# its own — plenty of legitimate sites use them — which is why it is worth few
# points and never bands a domain on its own.
SUSPICIOUS_TLDS = frozenset({"top", "xyz", "loan", "click", "work", "gq", "cf", "tk", "ml"})

# Anchor words that indicate a commercial placement rather than an editorial
# mention. Again weak alone; meaningful stacked with low authority.
MONEY_ANCHOR_TOKENS = frozenset(
    {
        "buy",
        "cheap",
        "discount",
        "coupon",
        "casino",
        "loan",
        "pills",
        "porn",
        "escort",
        "replica",
        "essay",
        "betting",
        "crypto",
        "forex",
    }
)

BAND_MEDIUM = 40
BAND_HIGH = 70


@dataclass(frozen=True)
class ToxicityReason:
    code: str
    label: str
    weight: int
    evidence: str

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "label": self.label,
            "weight": self.weight,
            "evidence": self.evidence,
        }


def band_for(score: int) -> str:
    if score >= BAND_HIGH:
        return "high"
    if score >= BAND_MEDIUM:
        return "medium"
    return "low"


def assess_domain(
    *,
    referring_domain: str,
    domain_authority: float | None,
    vendor_spam_score: float | None,
    tld: str | None,
    subnet: str | None,
    subnet_peers: int,
    anchors: list[str],
    follow_ratio: float,
) -> tuple[int, list[ToxicityReason]]:
    """Score one referring domain, returning the score and every reason for it.

    Deliberately additive and capped rather than multiplicative: a single strong
    signal should not be able to brand a domain on its own, and the reasons a
    user reads should sum to the number they see.
    """

    reasons: list[ToxicityReason] = []

    if vendor_spam_score is not None and vendor_spam_score >= 60:
        reasons.append(
            ToxicityReason(
                code="vendor_spam_score",
                label="The index's own spam score is high",
                weight=30,
                evidence=f"vendor spam score {vendor_spam_score:.0f}/100",
            )
        )

    if domain_authority is not None and domain_authority < 5:
        reasons.append(
            ToxicityReason(
                code="near_zero_authority",
                label="Referring domain has almost no measured authority",
                weight=20,
                evidence=f"domain authority {domain_authority:.0f}/100",
            )
        )

    if tld and tld.lower().lstrip(".") in SUSPICIOUS_TLDS:
        reasons.append(
            ToxicityReason(
                code="suspicious_tld",
                label="TLD is over-represented in link networks",
                weight=10,
                evidence=f".{tld.lower().lstrip('.')}",
            )
        )

    if subnet and subnet_peers >= 3:
        reasons.append(
            ToxicityReason(
                code="subnet_cluster",
                label="Several referring domains share one /24 network",
                weight=25,
                evidence=f"{subnet_peers} referring domains in {subnet}",
            )
        )

    money_anchors = [
        anchor
        for anchor in anchors
        if any(token in (anchor or "").lower() for token in MONEY_ANCHOR_TOKENS)
    ]
    if money_anchors and anchors:
        share = len(money_anchors) / len(anchors)
        if share >= 0.5:
            reasons.append(
                ToxicityReason(
                    code="money_anchor_density",
                    label="Most anchors from this domain are commercial phrases",
                    weight=20,
                    evidence=f"{len(money_anchors)} of {len(anchors)}: "
                    + ", ".join(sorted(set(money_anchors))[:3]),
                )
            )

    score = min(100, sum(reason.weight for reason in reasons))
    return score, reasons


def assess_project(
    session: Session,
    *,
    project_id: uuid.UUID,
    subject_domain: str,
) -> int:
    """Recompute toxicity for every referring domain of one subject.

    Returns how many domains were assessed. Called at the end of an import, so
    the score always reflects the profile it was computed from.
    """

    rollups = list(
        session.scalars(
            select(ReferringDomainRollup).where(
                ReferringDomainRollup.project_id == project_id,
                ReferringDomainRollup.subject_domain == subject_domain,
            )
        )
    )
    if not rollups:
        return 0

    subnet_counts: dict[str, int] = defaultdict(int)
    for rollup in rollups:
        if rollup.source_subnet and rollup.links_count > 0:
            subnet_counts[rollup.source_subnet] += 1

    anchors_by_domain: dict[str, list[str]] = defaultdict(list)
    spam_by_domain: dict[str, float | None] = {}
    tld_by_domain: dict[str, str | None] = {}
    for link in session.scalars(
        select(Backlink).where(
            Backlink.project_id == project_id,
            Backlink.subject_domain == subject_domain,
            Backlink.status == "active",
        )
    ):
        anchors_by_domain[link.source_domain].append(link.anchor)
        spam_by_domain.setdefault(link.source_domain, link.vendor_spam_score)
        tld_by_domain.setdefault(link.source_domain, link.tld)

    for rollup in rollups:
        if rollup.links_count <= 0:
            rollup.toxicity_score = None
            rollup.toxicity_band = None
            rollup.toxicity_reasons = None
            rollup.toxicity_version = TOXICITY_VERSION
            continue

        score, reasons = assess_domain(
            referring_domain=rollup.referring_domain,
            domain_authority=rollup.domain_authority,
            vendor_spam_score=spam_by_domain.get(rollup.referring_domain),
            tld=tld_by_domain.get(rollup.referring_domain),
            subnet=rollup.source_subnet,
            subnet_peers=subnet_counts.get(rollup.source_subnet or "", 0),
            anchors=anchors_by_domain.get(rollup.referring_domain, []),
            follow_ratio=(rollup.follow_links / rollup.links_count if rollup.links_count else 0.0),
        )
        rollup.toxicity_score = score
        rollup.toxicity_band = band_for(score)
        rollup.toxicity_reasons = [reason.as_dict() for reason in reasons]
        rollup.toxicity_version = TOXICITY_VERSION

    session.flush()
    return len(rollups)


DISAVOW_PREAMBLE = (
    "# Yanki disavow candidates — REVIEW BEFORE SUBMITTING.\n"
    "#\n"
    "# These are domains whose link patterns resemble those commonly associated\n"
    "# with link manipulation. They are NOT a judgement that any search engine\n"
    "# penalises them, and Yanki has not submitted anything on your behalf.\n"
    "# Disavowing a legitimate link removes real value, so every line below\n"
    "# carries the reasons it was flagged. Delete any you disagree with.\n"
    "#\n"
    "# Generated by Yanki (toxicity model {version}).\n"
)


def disavow_file(
    session: Session,
    *,
    project_id: uuid.UUID,
    subject_domain: str,
    minimum_band: str = "high",
) -> str:
    """A Google-format disavow file, with the reasoning kept in as comments.

    Google's format allows ``#`` comments, so the evidence rides along with the
    export rather than being lost the moment it leaves the product. Anyone
    reviewing the file can see why each domain is there — which is the whole
    point, given that submitting it is irreversible in effect.
    """

    wanted = {"high"} if minimum_band == "high" else {"high", "medium"}
    rollups = list(
        session.scalars(
            select(ReferringDomainRollup)
            .where(
                ReferringDomainRollup.project_id == project_id,
                ReferringDomainRollup.subject_domain == subject_domain,
                ReferringDomainRollup.links_count > 0,
            )
            .order_by(ReferringDomainRollup.toxicity_score.desc())
        )
    )

    lines = [DISAVOW_PREAMBLE.format(version=TOXICITY_VERSION)]
    flagged = 0
    for rollup in rollups:
        if (rollup.toxicity_band or "low") not in wanted:
            continue
        flagged += 1
        for reason in rollup.toxicity_reasons or []:
            lines.append(f"#   - {reason.get('label')}: {reason.get('evidence')}")
        lines.append(f"# {rollup.referring_domain}: score {rollup.toxicity_score}/100")
        lines.append(f"domain:{rollup.referring_domain}")
        lines.append("")

    if flagged == 0:
        lines.append("# No domains met the flagging threshold. Nothing to disavow.\n")

    return "\n".join(lines)
