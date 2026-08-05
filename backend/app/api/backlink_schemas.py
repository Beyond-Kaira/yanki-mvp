"""API contracts for Backlink Intelligence (Phase 8 / P8.3).

Two conventions carried through every model here, both traceable to the
module's central risk — that a confident number is the thing customers stop
trusting first:

* **Provenance travels with the data.** Every payload that reports a total also
  reports which index said so, when it was fetched, and whether that pull was
  measurable. A UI cannot label a number honestly with data it was never given.
* **Nullable means "not measured".** ``None`` for an authority or a toxicity
  score is a distinct answer from ``0`` and is serialized as such, so the
  frontend can render "—" rather than a confident zero.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

BacklinkStatus = Literal["active", "missing_pending", "lost", "lost_unverified"]
AnchorClass = Literal["exact", "partial", "brand", "naked", "generic"]
ToxicityBand = Literal["low", "medium", "high"]
LinkEventKind = Literal["new", "lost", "regained", "changed"]
InventorySort = Literal["authority", "first_seen", "last_seen", "toxicity", "domain"]
DomainSort = Literal["authority", "links", "toxicity", "domain"]


class BacklinkImportOut(BaseModel):
    id: uuid.UUID
    status: str
    vendor: str
    trigger: str
    coverage_status: str | None = None
    measurable: bool
    rows_ingested: int
    reported_total_backlinks: int | None = None
    reported_total_referring_domains: int | None = None
    new_in_period: int
    lost_in_period: int
    cost_usd: str
    snapshot_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    provenance: dict[str, Any] | None = None


class RefreshRequest(BaseModel):
    # Present so a scheduled refresh (P8.4's residual) can label its own runs
    # without a second endpoint. Rejected for anything but the two known values
    # rather than stored free-form, because it is read back as a filter.
    trigger: Literal["manual", "scheduled"] = "manual"


class RefreshOut(BaseModel):
    import_id: uuid.UUID
    measurable: bool
    coverage_status: str
    rows_ingested: int
    new_links: int
    lost_links: int
    regained_links: int
    changed_links: int
    cost_usd: Decimal


class AnchorDistributionOut(BaseModel):
    total: int
    counts: dict[str, int]
    shares: dict[str, float]
    money_anchor_share: float


class VelocityPointOut(BaseModel):
    at: str | None = None
    new: int
    lost: int
    reported_total: int | None = None
    measurable: bool
    authority: int | None = None


class BacklinkSummaryOut(BaseModel):
    subject_domain: str
    backlinks: int
    follow_links: int
    referring_domains: int
    lost_links: int
    authority: int | None = None
    authority_version: str | None = None
    # The decomposition, rendered verbatim on the methodology panel. Typed as a
    # bag because the formula is additively versioned — freezing its terms into
    # this schema would make publishing v2 a breaking API change.
    authority_components: dict[str, Any] | None = None
    last_import: BacklinkImportOut | None = None
    velocity: list[VelocityPointOut] = Field(default_factory=list)
    anchors: AnchorDistributionOut
    toxicity: dict[str, int]


class BacklinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_url: str
    source_domain: str
    target_url: str
    anchor: str
    anchor_class: str
    is_follow: bool
    is_image_link: bool
    tld: str | None = None
    status: str
    first_seen_at: datetime
    last_seen_at: datetime
    lost_at: datetime | None = None
    lost_reason: str | None = None
    verified_at: datetime | None = None
    verify_verdict: str | None = None
    source_domain_authority: float | None = None
    source_page_authority: float | None = None
    toxicity_score: int | None = None
    toxicity_band: str | None = None
    vendor: str


class BacklinkPageOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[BacklinkOut]


class ReferringDomainOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    referring_domain: str
    links_count: int
    follow_links: int
    first_linked_at: datetime | None = None
    last_linked_at: datetime | None = None
    domain_authority: float | None = None
    toxicity_score: int | None = None
    toxicity_band: str | None = None
    toxicity_version: str | None = None
    # Always sent with the score, never behind a second request: a flag whose
    # reasons are one click away is a flag people act on without reading them.
    toxicity_reasons: list[Any] | None = None


class ReferringDomainPageOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ReferringDomainOut]


class LinkEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    reason: str | None = None
    detected_by: str
    verified: bool
    source_url: str
    source_domain: str
    target_url: str
    # For a 'changed' event this carries the before/after the delta engine saw;
    # it is the only place the change itself is legible.
    detail: dict[str, Any] | None = None
    authority_at_event: float | None = None
    occurred_at: datetime


class LinkEventPageOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[LinkEventOut]


class GapRowOut(BaseModel):
    referring_domain: str
    linking_competitors: int
    competitor_domains: list[str]
    domain_authority: float | None = None
    score: float


class UnlinkedMentionOut(BaseModel):
    source_domain: str
    source_url: str
    evidence: str
    seen_via: str


class OpportunitiesOut(BaseModel):
    link_gap: list[GapRowOut]
    unlinked_mentions: list[UnlinkedMentionOut]
    provenance: dict[str, str]


class CompetitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    competitor_domain: str
    label: str | None = None
    active: bool
    tracked_since: datetime


class TrackCompetitorRequest(BaseModel):
    domain: str = Field(min_length=1, max_length=253)
    label: str | None = Field(default=None, max_length=120)

    @field_validator("domain")
    @classmethod
    def _domain_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("domain must not be blank")
        return normalized
