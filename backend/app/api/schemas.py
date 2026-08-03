"""Pydantic request/response schemas — the locked API contract.

The GET response always carries a ``result`` envelope; its inner fields are
null/empty until the pipeline produces them, so the frontend can render partial
state (and failures keep their partial results queryable — FR-7).
"""

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


class ResultOut(BaseModel):
    kyc: dict[str, Any] | None
    prompts: list[PromptOut]
    responses: list[ResponseOut]
    geo_score: float | None
    footprint_count: int | None
    total_responses: int | None
    # Checker-only read-time aggregates (P5.3); null for MVP / legacy rows.
    engine_presence: list[EnginePresence] | None
    competitors_appeared: list[CompetitorMention] | None
    # SERP visibility (ADR-28); null on every run that did not measure it.
    serp: SerpVisibilityOut | None


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
