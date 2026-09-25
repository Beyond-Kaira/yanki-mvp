"""Internal, read-only industry aggregation across organizations.

This is not an HTTP endpoint. Public output contains source URLs and aggregates,
never customer identities, question/answer text, or record identifiers.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.citations.evidence import canonical_url, inline_ranks, result_lookup, result_rank
from app.citations.report import provenance
from app.db.models import Analysis, GeoRecord, Response
from app.services.sectors import normalize_sector


def question_key(value: str) -> str:
    # Preserve punctuation and numbers: similar wording is not the same question.
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


class SourceCounts(BaseModel):
    response_count: int
    question_count: int
    response_coverage: float
    model_counts: dict[str, int]


class RankedPage(SourceCounts):
    url: str


class RankedSite(SourceCounts):
    domain: str
    page_count: int
    pages: list[RankedPage]


class IndustryRanking(BaseModel):
    sector: str
    scope: str = "GEO analyses of companies in this sector, across organizations."
    methodology: str = (
        "Stored sector labels; brand-probe questions excluded. Only explicitly live, "
        "Tavily-grounded answers with citations matching stored search results and inline "
        "markers contribute citations. Each answer counts once per site or page. "
        "Successful uncited answers remain in the coverage denominator. Repeated runs "
        "count separately; identical question text is counted once after case/space "
        "normalization. Sites are exact hostnames, not registrable domains."
    )
    candidate_responses: int = 0
    eligible_responses: int = 0
    distinct_questions: int = 0
    excluded_responses: dict[str, int] = Field(default_factory=dict)
    rejected_citations: dict[str, int] = Field(default_factory=dict)
    page_count: int = 0
    site_count: int = 0
    sites: list[RankedSite] = Field(default_factory=list)


class IndustrySector(BaseModel):
    sector: str
    record_count: int


class IndustryRankingPage(IndustryRanking):
    offset: int
    limit: int
    page_limit_per_site: int = 50


def list_industry_sectors(session: Session) -> list[IndustrySector]:
    return [
        IndustrySector(sector=sector, record_count=count)
        for sector, count in session.execute(
            select(GeoRecord.sector_key, func.count())
            .where(GeoRecord.sector_key.is_not(None))
            .group_by(GeoRecord.sector_key)
            .order_by(GeoRecord.sector_key)
        )
        if sector
    ]


@dataclass
class Bucket:
    responses: set[str] = field(default_factory=set)
    questions: set[str] = field(default_factory=set)
    models: dict[str, set[str]] = field(default_factory=dict)

    def add(self, response: str, question: str, model: str) -> None:
        self.responses.add(response)
        self.questions.add(question)
        self.models.setdefault(model, set()).add(response)

    def counts(self, denominator: int) -> dict:
        return {
            "response_count": len(self.responses),
            "question_count": len(self.questions),
            "response_coverage": round(100 * len(self.responses) / denominator, 2),
            "model_counts": {model: len(ids) for model, ids in sorted(self.models.items())},
        }


def build_industry_ranking(session: Session, sector: str) -> IndustryRanking:
    """Global internal report. Caller must authorize any future public exposure."""
    sector = normalize_sector(sector)
    if not sector or len(sector) > 200:
        raise ValueError("Enter a sector between 1 and 200 characters")
    report = IndustryRanking(sector=sector)
    excluded: Counter[str] = Counter()
    rejected: Counter[str] = Counter()
    questions: set[str] = set()
    pages: dict[str, Bucket] = {}
    sites: dict[str, Bucket] = {}
    site_pages: dict[str, set[str]] = {}
    # One GeoRecord per Response (unique FK). Never count the audit JSON twin.
    statement = (
        select(GeoRecord, Response.model, Response.audit, Analysis.status, Analysis.geo_run)
        .join(
            Response,
            (GeoRecord.response_id == Response.id)
            & (GeoRecord.analysis_id == Response.analysis_id),
        )
        .join(Analysis, GeoRecord.analysis_id == Analysis.id)
        .where(GeoRecord.sector_key == sector)
        .execution_options(yield_per=500)
    )
    for record, model, audit, status, run in session.execute(statement):
        report.candidate_responses += 1
        origin = provenance(run if isinstance(run, dict) else {})
        audit = audit if isinstance(audit, dict) else {}
        answer = record.grounded_answer
        reason = None
        if (record.prompt_group or "").strip().casefold() == "brand-probe":
            reason = "brand_probe"
        elif status != "done":
            reason = "analysis_not_complete"
        elif origin != "grounded":
            reason = "unknown_provenance" if origin == "unknown" else origin
        elif model == "mock" or audit.get("measurement_mode") in {"mock", "simulated"}:
            reason = "mock_or_simulated"
        elif audit.get("search_provider") == "mock":
            reason = "mock_or_simulated"
        elif record.error is not False or not isinstance(answer, str) or not answer.strip():
            reason = "failed_or_missing_answer"
        elif not record.prompt or not record.prompt.strip():
            reason = "missing_question"
        elif not isinstance(record.citations, list) or not (
            isinstance(record.search_results, list)
            or isinstance(record.search_results, dict)
            and isinstance(record.search_results.get("results"), list)
        ):
            reason = "missing_evidence"
        if reason:
            excluded[reason] += 1
            continue
        report.eligible_responses += 1
        question = question_key(record.prompt)
        questions.add(question)
        response_id = str(record.response_id)
        model = model or "unknown"
        lookup = result_lookup(record.search_results)
        markers = inline_ranks(answer)
        for citation in record.citations:
            if not isinstance(citation, dict):
                rejected["malformed_citation"] += 1
                continue
            rank = result_rank(citation.get("result_rank"))
            source = lookup.get(rank) if rank is not None else None
            url = canonical_url(source.get("url")) if source else None
            rejection = None
            if rank is None:
                rejection = "invalid_result_rank"
            elif source is None:
                rejection = "unmatched_result_rank"
            elif not url:
                rejection = "invalid_source_url"
            elif rank not in markers:
                rejection = "missing_inline_marker"
            elif citation.get("url") and canonical_url(citation["url"]) != url:
                rejection = "source_url_mismatch"
            if rejection:
                rejected[rejection] += 1
                continue
            assert url is not None
            host = urlsplit(url).hostname or ""
            pages.setdefault(url, Bucket()).add(response_id, question, model)
            sites.setdefault(host, Bucket()).add(response_id, question, model)
            site_pages.setdefault(host, set()).add(url)
    report.distinct_questions = len(questions)
    report.excluded_responses = dict(sorted(excluded.items()))
    report.rejected_citations = dict(sorted(rejected.items()))
    report.page_count = len(pages)
    report.site_count = len(sites)
    for domain, bucket in sites.items():
        children = [
            RankedPage(url=url, **pages[url].counts(report.eligible_responses))
            for url in sorted(site_pages[domain])
        ]
        children.sort(key=lambda p: (-p.response_count, -p.question_count, p.url))
        report.sites.append(
            RankedSite(
                domain=domain,
                page_count=len(children),
                pages=children,
                **bucket.counts(report.eligible_responses),
            )
        )
    report.sites.sort(key=lambda s: (-s.response_count, -s.question_count, s.domain))
    return report
