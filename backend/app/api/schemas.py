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

from pydantic import AfterValidator, AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

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
    """Credentials required to create a user account."""

    email: NormalizedEmail
    password: str = Field(min_length=8, max_length=128)


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
