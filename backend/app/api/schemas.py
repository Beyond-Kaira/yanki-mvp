"""Pydantic request/response schemas — the locked API contract.

The GET response always carries a ``result`` envelope; its inner fields are
null/empty until the pipeline produces them, so the frontend can render partial
state (and failures keep their partial results queryable — FR-7).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.services.auth import normalize_email

# Minimal email shape check. email-validator (pydantic[email]) is not installed
# and the card says not to add a heavy dep just for this — a conservative regex
# (one @, non-empty local/domain, a dotted TLD) is enough for the lead gate.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_and_validate_email(value: str) -> str:
    normalized = normalize_email(value)

    if not _EMAIL_RE.fullmatch(normalized):
        raise ValueError("invalid email")

    return normalized


NormalizedEmail = Annotated[
    str,
    AfterValidator(_normalize_and_validate_email),
]


class CreateAnalysisRequest(BaseModel):
    # AnyHttpUrl accepts http/https URLs only; anything else is a 422.
    url: AnyHttpUrl


class CreateAnalysisResponse(BaseModel):
    id: uuid.UUID


class CheckerSubmitRequest(BaseModel):
    """A public checker submit. brand+category must be non-empty after trim."""

    brand: str
    category: str
    lang: str = "en"

    @field_validator("brand", "category")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        # Reject blank/whitespace-only up front so the route records NOTHING
        # (this raises a 422 before create_checker_analysis runs).
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v


class CheckerSubmitResponse(BaseModel):
    id: uuid.UUID
    submission_id: uuid.UUID


class CheckerLeadRequest(BaseModel):
    submission_id: uuid.UUID
    email: str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError("invalid email")
        return v.strip()


class WaitlistRequest(BaseModel):
    """A public waitlist signup. The email is validated + normalized server-side
    (trim + lowercase) so a malformed address is a 422 before any row is written,
    and the stored value matches the unique lowercased column."""

    email: str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        normalized = v.strip().lower()
        if not _EMAIL_RE.match(normalized):
            raise ValueError("invalid email")
        return normalized


class WaitlistResponse(BaseModel):
    ok: bool


class SignupRequest(BaseModel):
    """Credentials required to create a user account.

    ``account_type`` decides what kind of organization the new user gets. Both
    kinds are real organizations with the same machinery behind them — an
    individual is not a special case with less structure, it is a company of
    one. That is what makes "convert to a team account" a rename plus an
    invitation rather than a data migration.
    """

    email: NormalizedEmail
    password: str = Field(min_length=8, max_length=128)
    account_type: Literal["individual", "organization"] = "individual"
    # Required when account_type is 'organization'; ignored otherwise. An
    # individual's org is named after their email local part.
    organization_name: str | None = Field(default=None, max_length=120)

    @field_validator("organization_name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        return value.strip() if value else None

    @model_validator(mode="after")
    def _organization_needs_a_name(self) -> SignupRequest:
        if self.account_type == "organization" and not self.organization_name:
            raise ValueError("organization_name is required for an organization account")
        return self


class LoginRequest(BaseModel):
    """Credentials required to authenticate a user."""

    email: NormalizedEmail
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    """Public user fields returned by authentication endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    created_at: datetime


class OrganizationOut(BaseModel):
    """The organization a request is acting within."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    kind: str
    status: str


class CurrentUserOut(UserOut):
    """``/auth/me`` — who you are AND what you can do.

    The role and permission list ride along so the UI can reflect authority
    without a second round trip. They are for RENDERING only: the API enforces
    every one of them independently, and a client that lies about its
    permissions gets a 403 exactly as before.
    """

    status: str
    organization: OrganizationOut | None = None
    role: str | None = None
    permissions: list[str] = Field(default_factory=list)


class LoginResponse(BaseModel):
    """Authenticated user and bearer token returned after login."""

    user: UserOut
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class RefreshResponse(BaseModel):
    """New bearer token returned after refresh-token rotation."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"


class PromptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text: str
    category: str


class ResponseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prompt_id: uuid.UUID
    engine: str
    model: str
    raw_text: str
    footprint: bool | None
    matched_snippet: str | None
    cost_usd: float
    audit: dict[str, Any] | None = None


class GeoRecordOut(BaseModel):
    """One Kaira-style audit record persisted columnar in ``geo_records``."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    response_id: uuid.UUID
    brand: str
    sector: str | None = None
    prompt: str
    prompt_group: str | None = None
    intent: str | None = None
    measurement_mode: str | None = None
    search_provider: str | None = None
    search_results: list[Any] | dict[str, Any] | None = None
    search_visibility: dict[str, Any] | None = None
    grounded_answer: str | None = None
    simulated_answer: str | None = None
    mentioned: bool | None = None
    rank_position: int | None = None
    mention_context: str | None = None
    competitors: list[Any] | None = None
    answer_summary: str | None = None
    recommendation_reasoning: str | None = None
    reasoning_trace: dict[str, Any] | None = None
    citations: list[Any] | None = None
    citation_metrics: dict[str, Any] | None = None
    visibility_drivers: dict[str, Any] | None = None
    visibility_gaps: dict[str, Any] | None = None
    trust_signals: list[Any] | None = None
    entities_associated_with_brand: list[Any] | None = None
    sentiment: str | None = None
    content_improvement_opportunities: list[Any] | None = None
    model: str | None = None
    generated_at: datetime | None = None
    error: bool | None = None
    schema_version: str | None = None
    owned_domains: list[Any] | None = None

    @field_validator(
        "competitors",
        "citations",
        "trust_signals",
        "entities_associated_with_brand",
        "content_improvement_opportunities",
        "owned_domains",
        mode="before",
    )
    @classmethod
    def _coerce_str_to_list(cls, value: Any) -> Any:
        # Live LLM rows sometimes store a bare string instead of a list.
        if value is None or isinstance(value, list):
            return value
        if isinstance(value, str):
            return [value] if value.strip() else []
        return [value]


class EnginePresence(BaseModel):
    """One engine's presence in a checker run: ``mentioned`` of ``total`` answers
    named the searched brand (P5.3). Read-time aggregate of the ``footprint``
    booleans; the per-engine totals sum to ``total_responses``."""

    model_config = ConfigDict(from_attributes=True)

    engine: str
    mentioned: int
    total: int


class CompetitorMention(BaseModel):
    """A competitor brand that showed up in the answers and how many answers
    named it (P5.3) — a proper-noun co-mention over the raw text, not the KYC
    competitor list."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    mentions: int


class SerpCheckOut(BaseModel):
    """One search query run for an analysis, and what the results page showed.

    ``hit`` is nullable and the distinction matters to anyone reading this: NULL
    is a page we could not read (the search instance was unreachable, or every
    upstream engine refused it) and is excluded from the score; ``false`` is a
    real, counted miss.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query: str
    source: str
    hit: bool | None
    rank: int | None
    matched_url: str | None
    matched_snippet: str | None
    matched_via: str | None
    result_count: int
    unresponsive_engines: str | None


class SerpVisibilityOut(BaseModel):
    """SERP visibility for one analysis (ADR-28).

    Present only on runs where the feature was switched on; ``ResultOut.serp``
    stays null otherwise, so "we did not look" is never rendered as a zero.
    ``score`` is separately nullable *within* a present summary: that is the run
    where we did look and could not read the results.
    """

    status: str
    source: str | None
    score: float | None
    hits: int
    queries: int
    checks: list[SerpCheckOut]


class SeoCheckOut(BaseModel):
    """One SEO / AI-readiness check and the evidence behind its verdict.

    ``status`` is one of ``pass`` / ``warn`` / ``fail`` / ``not_measured`` /
    ``not_applicable``. The last two are excluded from the score and mean
    different things — "we could not read the input" versus "this does not apply
    here" — so the UI must not collapse them into each other or into a failure.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    check_id: str
    title: str
    severity: str
    status: str
    detail: str | None
    evidence: str | None


class SeoAuditOut(BaseModel):
    """The SEO audit for one analysis (ADR-31).

    ``grade`` is the headline rather than ``score``, because a weighted average
    can hide a fatal problem: the grade is capped by critical failures, so a site
    that blocks AI crawlers cannot present as healthy. Null on runs that did not
    audit — a checker submission has no site to look at.
    """

    status: str
    score: float | None
    grade: str | None
    checks: list[SeoCheckOut]


class ResultOut(BaseModel):
    kyc: dict[str, Any] | None
    prompts: list[PromptOut]
    responses: list[ResponseOut]
    # Composite GEO on 0–100 (measured path). Legacy rows may still be 0–1.
    geo_score: float | None
    footprint_count: int | None
    total_responses: int | None
    reliability_score: float | None = None
    interventions: list[dict[str, Any]] | dict[str, Any] | None = None
    citation_summary: dict[str, Any] | None = None
    geo_records: list[GeoRecordOut] = []
    # Checker-only read-time aggregates (P5.3); null for MVP / legacy rows.
    engine_presence: list[EnginePresence] | None
    competitors_appeared: list[CompetitorMention] | None
    # SERP visibility (ADR-28); null on every run that did not measure it.
    serp: SerpVisibilityOut | None
    # SEO / AI-readiness audit (ADR-31); null on every run that did not audit.
    seo: SeoAuditOut | None


class AnalysisOut(BaseModel):
    id: uuid.UUID
    url: str
    status: str
    progress: int
    current_step: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    result: ResultOut


class AdminMemberOut(BaseModel):
    """One member of an organization, as an administrator sees them."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    status: str
    created_at: datetime
    last_active_at: datetime | None = None
    role: str
    membership_status: str
    membership_id: uuid.UUID


class AdminUserListOut(BaseModel):
    """A page of members, plus what the UI needs to render its controls.

    ``assignable_roles`` ships with the list so the role picker is populated
    from the server's idea of what may be assigned rather than a hardcoded
    frontend copy that drifts. Platform roles are excluded there, so a customer
    cannot even be offered one.
    """

    total: int
    limit: int
    offset: int
    assignable_roles: list[str]
    members: list[AdminMemberOut]


class AdminMemberUpdateRequest(BaseModel):
    """Change a member's role, their account status, or both.

    Both optional: a PATCH that sets neither is a no-op rather than an error,
    which keeps a form that only touched one field simple to submit.
    """

    role: str | None = Field(default=None, max_length=40)
    status: str | None = Field(default=None, max_length=20)


class AdminOrganizationOut(BaseModel):
    """The caller's organization."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    kind: str
    status: str
    created_at: datetime
    member_count: int


# --- Invitations ----------------------------------------------------------


class AdminInvitationOut(BaseModel):
    """One invitation, as an administrator sees it.

    Note what is absent: the token. It exists in the email and nowhere else, so
    this response cannot be replayed into a working invitation even by the
    administrator who created it. ``accept_url`` on the create response is the
    single deliberate exception, and it is returned exactly once.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str
    status: str
    # Derived, not stored: an invitation is expired when its clock says so, not
    # when a sweeper gets around to relabelling it.
    expired: bool
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    last_sent_at: datetime | None = None
    sent_count: int
    invited_by_email: str | None = None


class AdminInvitationListOut(BaseModel):
    """A page of invitations, plus the roles this caller may hand out."""

    total: int
    limit: int
    offset: int
    assignable_roles: list[str]
    invitations: list[AdminInvitationOut]


class AdminInvitationCreateRequest(BaseModel):
    """Invite one person to the caller's organization."""

    email: NormalizedEmail
    role: str = Field(max_length=40)


class AdminInvitationCreatedOut(BaseModel):
    """The created invitation and the one-time link that accepts it.

    ``accept_url`` is returned so an administrator can pass the link on directly
    when email is not configured — which is the case for any fresh deployment,
    and would otherwise make invitations silently useless. It is the only
    response in the API that carries an invitation token, it is never returned
    again, and issuing it is audit-logged like everything else here.
    """

    invitation: AdminInvitationOut
    accept_url: str
    email_sent: bool


class InvitationPreviewOut(BaseModel):
    """What an invited person is told before they commit to signing up.

    Carries the organization name and the offered role so the accept screen can
    say what is actually being joined. It carries the invited **email** too:
    that address is already known to whoever holds the link (it was sent to
    them), so echoing it leaks nothing and lets the form prefill.
    """

    email: str
    role: str
    organization_name: str
    expires_at: datetime


class InvitationAcceptRequest(BaseModel):
    """Create an account from an invitation.

    The password is the only field: the email comes from the invitation, so an
    invitation cannot be redirected to a different address by editing the form.
    """

    password: str = Field(min_length=8, max_length=128)


# --- Audit log ------------------------------------------------------------


class AuditEventOut(BaseModel):
    """One audit event.

    ``before``/``after`` arrive already redacted — the redaction happened at
    write time, so there is no unredacted copy for this endpoint to leak.
    ``integrity`` is this row's self-hash verdict: ``ok`` intact, ``altered``
    if the stored content no longer matches its hash, ``unverifiable`` for rows
    written before hashing existed.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    occurred_at: datetime
    action: str
    outcome: str
    actor_type: str
    actor_id: uuid.UUID | None = None
    actor_label: str | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    changed: dict[str, Any] | None = None
    ip_hash: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
    integrity: Literal["ok", "altered", "unverifiable"]


class AuditEventListOut(BaseModel):
    """A page of audit events, plus what the filter UI needs to render itself."""

    total: int
    limit: int
    offset: int
    sort: str
    order: Literal["asc", "desc"]
    actions: list[str]
    events: list[AuditEventOut]


class AuditIntegrityOut(BaseModel):
    """The result of re-hashing recent audit rows.

    ``altered`` above zero means somebody edited the audit table out of band,
    which is the one number on this response worth alerting on.
    """

    checked: int
    intact: int
    altered: int
    unverifiable: int
    altered_ids: list[uuid.UUID]
    ok: bool
