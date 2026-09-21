"""Request/response schemas for standalone brand context (KYC) profiles — mod-5."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BrandContextOut(BaseModel):
    """One durable brand profile row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID | None
    created_by_user_id: uuid.UUID | None
    source_url: str | None
    brand: str
    domain: str | None
    locale: str
    category: str | None
    competitors: list[str]
    profile: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class CreateBrandContextRequest(BaseModel):
    """Create a profile from a URL (extract) or manual fields."""

    model_config = ConfigDict(extra="forbid")

    source_url: str | None = None
    brand: str | None = None
    domain: str | None = None
    locale: str = "en"
    category: str | None = None
    competitors: list[str] | None = None
    description: str | None = None
    industry: str | None = None
    aliases: list[str] | None = None
    products: list[str] | None = None
    services: list[str] | None = None
    keywords: list[str] | None = None
    use_cases: list[str] | None = None
    locations: list[str] | None = None

    @model_validator(mode="after")
    def _require_source_or_brand(self) -> CreateBrandContextRequest:
        if not (self.source_url or (self.brand or "").strip()):
            raise ValueError("source_url or brand is required")
        return self


class PatchBrandContextRequest(BaseModel):
    """Partial profile edit — does not start GEO or any other module run."""

    model_config = ConfigDict(extra="forbid")

    brand: str | None = None
    domain: str | None = None
    locale: str | None = None
    category: str | None = None
    competitors: list[str] | None = None
    description: str | None = None
    industry: str | None = None
    aliases: list[str] | None = None
    products: list[str] | None = None
    services: list[str] | None = None
    keywords: list[str] | None = None
    use_cases: list[str] | None = None
    locations: list[str] | None = None

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> PatchBrandContextRequest:
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        return self


class ExtractBrandContextRequest(BaseModel):
    """Enqueue async KYC extraction for an existing profile (mod-6)."""

    model_config = ConfigDict(extra="forbid")

    source_url: str | None = None


class ModuleRunOut(BaseModel):
    """One standalone module job row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_kind: str
    status: str
    progress: int
    current_step: str | None
    error: str | None
    org_id: uuid.UUID | None
    brand_context_id: uuid.UUID | None
    linked_analysis_id: uuid.UUID | None
    payload: dict[str, Any]
    result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
