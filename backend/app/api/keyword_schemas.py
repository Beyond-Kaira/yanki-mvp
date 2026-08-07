"""HTTP schemas for Keyword Research preview (OSS path)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class KeywordExpandRequest(BaseModel):
    seed: str = Field(..., min_length=1, max_length=120)
    locale: str = Field(default="en", min_length=2, max_length=32)
    exclude_brands: list[str] = Field(default_factory=list, max_length=20)
    max_ideas: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="Omit to use server KEYWORD_MAX_IDEAS.",
    )

    @field_validator("seed")
    @classmethod
    def _seed_not_blank(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("seed must not be blank")
        return cleaned

    @field_validator("locale")
    @classmethod
    def _locale_strip(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("locale must not be blank")
        return cleaned


class KeywordIdeaOut(BaseModel):
    phrase: str
    source: str
    signals: dict[str, Any] = Field(default_factory=dict)


class KeywordExpandResponse(BaseModel):
    seed: str
    locale: str
    provider: str
    ideas: list[KeywordIdeaOut]
    estimated: bool = Field(
        default=True,
        description="True while demand/difficulty are proxies, not licensed metrics.",
    )


class KeywordOverviewRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=120)
    locale: str = Field(default="en", min_length=2, max_length=32)
    exclude_brands: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("keyword")
    @classmethod
    def _keyword_not_blank(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("keyword must not be blank")
        return cleaned


class KeywordOverviewResponse(BaseModel):
    keyword: str
    locale: str
    provider: str
    signals: dict[str, Any] = Field(default_factory=dict)
    sample_ideas: list[KeywordIdeaOut] = Field(default_factory=list)
    estimated: bool = True


class KeywordRankCheckRequest(BaseModel):
    domain: str = Field(..., min_length=1, max_length=255)
    queries: list[str] = Field(..., min_length=1, max_length=20)
    locale: str = Field(default="en", min_length=2, max_length=32)

    @field_validator("domain")
    @classmethod
    def _domain_not_blank(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("domain must not be blank")
        return cleaned

    @field_validator("queries")
    @classmethod
    def _queries_non_empty_items(cls, value: list[str]) -> list[str]:
        cleaned = [" ".join(q.split()).strip() for q in value]
        cleaned = [q for q in cleaned if q]
        if not cleaned:
            raise ValueError("queries must include at least one non-blank phrase")
        return cleaned


class KeywordRankHitOut(BaseModel):
    query: str
    measurable: bool
    appeared: bool | None = None
    rank: int | None = None
    matched_url: str | None = None
    matched_via: str | None = None


class KeywordRankCheckResponse(BaseModel):
    domain: str
    provider: str
    results: list[KeywordRankHitOut]
