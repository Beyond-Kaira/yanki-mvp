"""Public contract for one analysis's citation report."""

from typing import Literal

from pydantic import BaseModel, Field

Ownership = Literal["owned", "competitor", "third_party"]
ReportView = Literal["pages", "domains"]
Provenance = Literal["grounded", "simulated", "mock", "unknown"]


class CitationEvidence(BaseModel):
    response_id: str
    prompt_id: str
    prompt: str
    model: str
    answer: str
    source_url: str
    result_rank: int
    observed_at: str | None
    mentioned: bool | None
    competitors: list[str]


class CitationSourceRow(BaseModel):
    key: str
    url: str | None
    title: str
    domain: str
    ownership: Ownership
    response_count: int
    prompt_count: int
    page_count: int
    response_coverage: float | None
    models: list[str]
    evidence: list[CitationEvidence]


class CitationScope(BaseModel):
    analysis_id: str
    sector: str | None
    observed_at: str | None
    provenance: Provenance
    models: list[str]
    prompt_groups: list[str]
    competitor_domains: list[str]


class CitationCoverage(BaseModel):
    eligible_responses: int = 0
    eligible_prompts: int = 0
    excluded_responses: int = 0
    rejected_citations: int = 0
    exclusion_reasons: dict[str, int] = Field(default_factory=dict)
    rejection_reasons: dict[str, int] = Field(default_factory=dict)


class CitationSummary(BaseModel):
    pages: int
    domains: int


class CitationSourcesOut(BaseModel):
    scope: CitationScope
    methodology: str
    coverage: CitationCoverage
    summary: CitationSummary
    rows: list[CitationSourceRow]
    total: int
    offset: int
    limit: int
