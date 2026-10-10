"""Aggregate only evidenced citations. Every filter shares this one count path."""

from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import urlsplit

from app.citations.evidence import (
    canonical_url,
    domain_matches,
    inline_ranks,
    result_lookup,
    result_rank,
)
from app.citations.schemas import (
    CitationCoverage,
    CitationEvidence,
    CitationScope,
    CitationSourceRow,
    CitationSourcesOut,
    CitationSummary,
    Ownership,
    Provenance,
    ReportView,
)
from app.db.models import Analysis

METHODOLOGY = (
    "Citations in model answers grounded in shared Tavily search results. "
    "Not observations of ChatGPT or Google AI Mode. Each page or domain is counted "
    "once per successful prompt × model answer. Coverage includes successful answers "
    "with no citations. Scope is this analysis's question set, not the entire industry."
)


def strings(value: Any) -> list[str]:
    return [v for v in value if isinstance(v, str) and v] if isinstance(value, list) else []


def competitor_hosts(raw: str) -> set[str]:
    hosts: set[str] = set()
    for item in raw.split(","):
        item = item.strip().lower()
        if not item:
            continue
        url = canonical_url(item if "://" in item else "https://" + item)
        if url is None:
            raise ValueError("Enter valid competitor domains separated by commas.")
        parsed = urlsplit(url)
        if parsed.path != "/" or parsed.query or parsed.port:
            raise ValueError("Enter competitor domains without paths, ports or query strings.")
        hosts.add(parsed.hostname or "")
    return hosts


def provenance(run: dict[str, Any]) -> Provenance:
    if run.get("dry_run") is True:
        return "mock"
    if run.get("mode") == "simulated":
        return "simulated"
    search = run.get("search")
    if (
        run.get("mode") == "measured"
        and run.get("dry_run") is False
        and isinstance(search, dict)
        and search.get("provider") == "tavily"
    ):
        return "grounded"
    return "unknown"


def build_citation_report(
    analysis: Analysis,
    *,
    view: ReportView = "pages",
    model: str = "",
    prompt_group: str = "",
    ownership: Ownership | None = None,
    q: str = "",
    competitor_domains: str = "",
    opportunities: bool = False,
    offset: int = 0,
    limit: int = 25,
) -> CitationSourcesOut:
    run = analysis.geo_run if isinstance(analysis.geo_run, dict) else {}
    origin = provenance(run)
    profile = analysis.kyc if isinstance(analysis.kyc, dict) else {}
    rivals = competitor_hosts(competitor_domains)
    target = canonical_url(analysis.url)
    owned = {urlsplit(target).hostname or ""} if target else set()
    # www aliases follow the same owned-domain contract used by the pipeline.
    owned |= {host.removeprefix("www.") for host in owned}
    known_competitors = {name.casefold() for name in strings(profile.get("competitors"))}
    prompts = {str(p.id): p for p in analysis.prompts}
    coverage = CitationCoverage()
    reasons: Counter[str] = Counter()
    rejection_reasons: Counter[str] = Counter()
    prompt_ids: set[str] = set()
    pages: dict[str, dict[str, Any]] = {}
    groups = sorted({p.category or "general" for p in analysis.prompts})
    models = sorted({r.model or "unknown" for r in analysis.responses})

    # Response.audit is the original of the GeoRecord twin; reading it once
    # avoids counting both stored representations and preserves prompt/model ids.
    for response in analysis.responses:
        response_model = response.model or "unknown"
        prompt = prompts.get(str(response.prompt_id))
        group = (prompt.category or "general") if prompt else "general"
        if model and model != response_model or prompt_group and prompt_group != group:
            continue
        audit = response.audit if isinstance(response.audit, dict) else {}
        answer = audit.get("grounded_answer")
        exclusion: str | None = None
        if origin != "grounded":
            exclusion = origin
        elif (
            response_model == "mock"
            or audit.get("measurement_mode") == "mock"
            or audit.get("search_provider") == "mock"
        ):
            exclusion = "mock"
        elif audit.get("error") is not False or not isinstance(answer, str) or not answer.strip():
            exclusion = "failed_or_unverified_answer"
        elif prompt is None:
            exclusion = "missing_prompt"
        elif not isinstance(audit.get("citations"), list):
            exclusion = "unverified_source_record"
        elif not (
            isinstance(audit.get("search_results"), list)
            or isinstance(audit.get("search_results"), dict)
            and isinstance(audit["search_results"].get("results"), list)
        ):
            exclusion = "unverified_source_record"
        if exclusion:
            reasons[exclusion] += 1
            coverage.excluded_responses += 1
            continue
        assert isinstance(answer, str) and prompt is not None
        coverage.eligible_responses += 1
        prompt_ids.add(str(response.prompt_id))
        lookup = result_lookup(audit.get("search_results"))
        ranks_in_answer = inline_ranks(answer)
        seen: set[str] = set()
        citations = audit.get("citations")
        for citation in citations if isinstance(citations, list) else []:
            if not isinstance(citation, dict):
                coverage.rejected_citations += 1
                rejection_reasons["malformed_citation"] += 1
                continue
            rank = result_rank(citation.get("result_rank"))
            source = lookup.get(rank) if rank is not None else None
            url = canonical_url(source.get("url")) if source else None
            if rank is None:
                coverage.rejected_citations += 1
                rejection_reasons["invalid_result_rank"] += 1
                continue
            if source is None:
                coverage.rejected_citations += 1
                rejection_reasons["unmatched_result_rank"] += 1
                continue
            if not url:
                coverage.rejected_citations += 1
                rejection_reasons["invalid_source_url"] += 1
                continue
            if rank not in ranks_in_answer:
                coverage.rejected_citations += 1
                rejection_reasons["missing_inline_marker"] += 1
                continue
            # Older LLM-proposed URLs must agree with stored search evidence.
            proposed = citation.get("url")
            if proposed and canonical_url(proposed) != url:
                coverage.rejected_citations += 1
                rejection_reasons["source_url_mismatch"] += 1
                continue
            if url in seen:
                continue
            seen.add(url)
            host = urlsplit(url).hostname or ""
            owner: Ownership = (
                "owned"
                if domain_matches(host, owned)
                else "competitor"
                if domain_matches(host, rivals)
                else "third_party"
            )
            competitors = strings(audit.get("competitors"))
            mentioned = audit.get("mentioned") if isinstance(audit.get("mentioned"), bool) else None
            if opportunities and not (
                owner == "third_party"
                and mentioned is False
                and any(c.casefold() in known_competitors for c in competitors)
            ):
                continue
            if ownership and owner != ownership:
                continue
            title = source.get("title") if isinstance(source.get("title"), str) else url
            if q and q.casefold() not in f"{url} {title}".casefold():
                continue
            page = pages.setdefault(
                url, {"title": title, "domain": host, "ownership": owner, "evidence": []}
            )
            page["evidence"].append(
                CitationEvidence(
                    response_id=str(response.id),
                    prompt_id=str(response.prompt_id),
                    prompt=prompt.text,
                    model=response_model,
                    answer=answer,
                    source_url=source["url"],
                    result_rank=rank,
                    observed_at=response.created_at.isoformat() if response.created_at else None,
                    mentioned=mentioned,
                    competitors=competitors,
                )
            )
    coverage.eligible_prompts = len(prompt_ids)
    coverage.exclusion_reasons = dict(reasons)
    coverage.rejection_reasons = dict(rejection_reasons)
    buckets: dict[str, dict[str, Any]] = {}
    for url, page in pages.items():
        key = url if view == "pages" else page["domain"]
        bucket = buckets.setdefault(key, {**page, "evidence": [], "pages": set()})
        bucket["pages"].add(url)
        bucket["evidence"].extend(page["evidence"])
    rows = []
    for key, bucket in buckets.items():
        evidence = sorted(bucket["evidence"], key=lambda e: (e.prompt_id, e.model, e.source_url))
        responses = {e.response_id for e in evidence}
        count = len(responses)
        rows.append(
            CitationSourceRow(
                key=key,
                url=key if view == "pages" else None,
                title=bucket["title"] if view == "pages" else key,
                domain=bucket["domain"],
                ownership=bucket["ownership"],
                response_count=count,
                prompt_count=len({e.prompt_id for e in evidence}),
                page_count=len(bucket["pages"]),
                response_coverage=round(100 * count / coverage.eligible_responses, 2)
                if coverage.eligible_responses
                else None,
                models=sorted({e.model for e in evidence}),
                evidence=evidence,
            )
        )
    rows.sort(key=lambda row: (-row.response_count, -row.prompt_count, row.key))
    return CitationSourcesOut(
        scope=CitationScope(
            analysis_id=str(analysis.id),
            sector=profile.get("industry") or None,
            observed_at=run.get("generated_at"),
            provenance=origin,
            models=models,
            prompt_groups=groups,
            competitor_domains=sorted(rivals),
        ),
        methodology=METHODOLOGY,
        coverage=coverage,
        summary=CitationSummary(
            pages=len(pages), domains=len({p["domain"] for p in pages.values()})
        ),
        rows=rows[offset : offset + limit],
        total=len(rows),
        offset=offset,
        limit=limit,
    )
