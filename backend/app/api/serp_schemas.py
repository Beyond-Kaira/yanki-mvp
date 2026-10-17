"""Standalone SERP visibility module runs — mod-3."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateSerpRunRequest(BaseModel):
    """Enqueue a SERP visibility run for an existing brand context."""

    model_config = ConfigDict(extra="forbid")

    brand_context_id: uuid.UUID
    queries: list[str] | None = Field(
        default=None,
        max_length=20,
        description="Optional explicit search queries (brand-free). Omit to derive from profile topics.",
    )
    locale: str = Field(default="en", max_length=16)

    @field_validator("queries")
    @classmethod
    def _strip_queries(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [q.strip() for q in value if q.strip()]
        if not cleaned:
            raise ValueError("queries must not be empty when provided")
        return cleaned
