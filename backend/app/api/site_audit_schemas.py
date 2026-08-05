"""API contracts for user-owned SEO projects and their Site Audit runs."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AuditProfileId = Literal["site_audit_mobile", "site_audit_desktop"]
SiteAuditStatus = Literal["queued", "running", "done", "failed"]
SiteAuditStep = Literal["discovery", "crawl", "analysis", "finalize"]
SiteAuditSeverity = Literal["error", "warning", "notice"]


class SiteAuditSettingsRequest(BaseModel):
    page_limit: int = Field(default=10, ge=1, le=500)
    profile_id: AuditProfileId = "site_audit_mobile"
    js_rendering: bool = True


class CreateSeoProjectRequest(SiteAuditSettingsRequest):
    domain: str = Field(min_length=1, max_length=2048)
    name: str | None = Field(default=None, max_length=120)

    @field_validator("domain")
    @classmethod
    def _domain_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("domain must not be blank")
        return normalized

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized


class SiteAuditIssueOut(BaseModel):
    code: str
    severity: SiteAuditSeverity
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class SiteAuditSchemaDetailsOut(BaseModel):
    valid_fields: list[str] = Field(default_factory=list)
    invalid_fields: list[str] = Field(default_factory=list)


class SiteAuditSchemaOut(BaseModel):
    type: str
    syntax_valid: bool
    structure_status: str
    details: SiteAuditSchemaDetailsOut = Field(default_factory=SiteAuditSchemaDetailsOut)
    error_detail: str | None = None


class SiteAuditPageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requested_url: str
    final_url: str
    status_code: int
    title: str
    h1_count: int
    meta_description: str | None
    html_lang: str | None
    issues: list[SiteAuditIssueOut]
    schemas: list[SiteAuditSchemaOut]


class SiteAuditSummaryOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    status: SiteAuditStatus
    progress: int
    current_step: SiteAuditStep | None
    error: str | None
    page_limit: int
    profile_id: AuditProfileId
    js_rendering: bool
    pages_discovered: int
    pages_crawled: int
    total_errors: int
    total_warnings: int
    total_notices: int
    health_score: int | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class SiteAuditDetailOut(SiteAuditSummaryOut):
    pages: list[SiteAuditPageOut]


class SeoProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    domain: str
    created_at: datetime
    updated_at: datetime
    latest_audit: SiteAuditSummaryOut | None


class SeoProjectDetailOut(SeoProjectOut):
    audits: list[SiteAuditSummaryOut]
