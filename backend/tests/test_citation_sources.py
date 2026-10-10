"""Counts, source evidence, provenance, filtering and the public report contract."""

from __future__ import annotations

import copy

import pytest

from app.citations.evidence import canonical_url
from app.citations.report import build_citation_report
from app.db.models import Prompt, Response
from app.pipeline.llm_analytics_measured import normalize_grounded_citations


@pytest.fixture()
def citation_analysis(db_session, make_analysis):
    analysis = make_analysis(
        url="https://acme.test",
        status="done",
        progress=100,
        geo_run={
            "mode": "measured",
            "dry_run": False,
            "search": {"provider": "tavily"},
            "generated_at": "2026-09-17T10:00:00+00:00",
        },
        kyc={"industry": "Software", "competitors": ["Rival"]},
    )
    prompts = [
        Prompt(analysis_id=analysis.id, text=text, category=group)
        for text, group in [("Best tools?", "recommendation"), ("How to choose?", "informational")]
    ]
    db_session.add_all(prompts)
    db_session.flush()
    sources = [
        {"rank": 1, "url": "https://publisher.test/guide?utm_source=ai", "title": "Guide"},
        {"rank": 2, "url": "https://publisher.test/other", "title": "Other"},
        {"rank": 3, "url": "https://acme.test/product", "title": "Product"},
        {"rank": 4, "url": "https://rival.test/product", "title": "Rival product"},
    ]
    for index, (model, answer, ranks) in enumerate(
        [
            ("model-a", "Rival is an option [1, 2, 3, 4].", [1, 1, 2, 3, 4]),
            ("model-b", "See the guide [1].", [1]),
            ("model-a", "No cited sources.", []),
            ("model-a", "", []),
        ]
    ):
        db_session.add(
            Response(
                analysis_id=analysis.id,
                prompt_id=prompts[index % 2].id,
                llm_provider="openrouter",
                model=model,
                raw_text=answer,
                audit={
                    "error": index == 3,
                    "grounded_answer": answer,
                    "mentioned": False,
                    "competitors": ["Rival"],
                    "search_results": sources,
                    "citations": [{"result_rank": rank} for rank in ranks],
                },
            )
        )
    db_session.commit()
    return analysis


def test_page_counts_deduplicate_responses_and_keep_uncited_answers(citation_analysis):
    report = build_citation_report(citation_analysis)
    assert report.coverage.eligible_responses == 3
    assert report.coverage.eligible_prompts == 2
    assert report.coverage.excluded_responses == 1
    guide = next(r for r in report.rows if r.title == "Guide")
    assert guide.url == "https://publisher.test/guide"
    assert guide.response_count == 2
    assert guide.prompt_count == 2
    assert guide.response_coverage == 66.67
    assert len(guide.evidence) == 2
    assert report.summary.pages == 4


def test_domains_count_response_once_even_with_two_pages(citation_analysis):
    report = build_citation_report(citation_analysis, view="domains")
    publisher = next(r for r in report.rows if r.domain == "publisher.test")
    assert publisher.response_count == 2
    assert publisher.page_count == 2
    assert len(publisher.evidence) == 3


def test_model_filter_changes_denominator_and_pagination(citation_analysis):
    report = build_citation_report(citation_analysis, model="model-a", q="guide", limit=1)
    assert report.coverage.eligible_responses == 2
    assert report.rows[0].response_coverage == 50
    assert report.total == 1
    assert build_citation_report(citation_analysis, q="guide", offset=1).rows == []
    assert build_citation_report(citation_analysis, model="absent").coverage.eligible_responses == 0


def test_ownership_uses_explicit_domains_not_competitor_names(citation_analysis):
    report = build_citation_report(citation_analysis, competitor_domains="rival.test")
    assert next(r for r in report.rows if r.domain == "rival.test").ownership == "competitor"
    assert next(r for r in report.rows if r.domain == "acme.test").ownership == "owned"
    owned = build_citation_report(citation_analysis, ownership="owned")
    assert len(owned.rows) == 1


@pytest.mark.parametrize(
    "run,origin",
    [
        ({}, "unknown"),
        ({"mode": "measured", "search": {"provider": "tavily"}}, "unknown"),
        ({"mode": "measured", "dry_run": True}, "mock"),
        ({"mode": "simulated", "dry_run": False}, "simulated"),
    ],
)
def test_non_live_runs_cannot_enter_rankings(citation_analysis, run, origin):
    citation_analysis.geo_run = run
    report = build_citation_report(citation_analysis)
    assert report.scope.provenance == origin
    assert report.rows == []
    assert report.coverage.eligible_responses == 0
    assert report.coverage.excluded_responses == 4


def test_sources_must_exist_be_cited_inline_and_match_url(citation_analysis):
    response = citation_analysis.responses[0]
    audit = copy.deepcopy(response.audit)
    audit["citations"] = [
        {"result_rank": 999},
        {"result_rank": True},
        "garbage",
        {"result_rank": 1, "url": "https://invented.test/"},
        {"result_rank": 2},
    ]
    audit["grounded_answer"] = "Only the guide [1]."
    response.audit = audit
    report = build_citation_report(citation_analysis, model="model-a")
    assert report.rows == []
    assert report.coverage.rejected_citations == 5
    assert report.coverage.rejection_reasons == {
        "unmatched_result_rank": 1,
        "invalid_result_rank": 1,
        "malformed_citation": 1,
        "source_url_mismatch": 1,
        "missing_inline_marker": 1,
    }


def test_opportunities_preserve_unknown_mentions(citation_analysis):
    report = build_citation_report(
        citation_analysis, opportunities=True, competitor_domains="rival.test"
    )
    assert {r.domain for r in report.rows} == {"publisher.test"}
    for response in citation_analysis.responses:
        response.audit = {**response.audit, "mentioned": None}
    assert build_citation_report(citation_analysis, opportunities=True).rows == []


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://EXAMPLE.test:443/Guide?a=1&utm_source=x#part", "https://example.test/Guide?a=1"),
        ("https://example.test/guide?a=2&a=1", "https://example.test/guide?a=2&a=1"),
        ("https://example.test/Guide/", "https://example.test/Guide/"),
        ("javascript:alert(1)", None),
        ("https://user:pass@example.test", None),
        ("https://example.test:bad/", None),
        ("https://example.test/\n", None),
    ],
)
def test_conservative_url_identity(raw, expected):
    assert canonical_url(raw) == expected


def test_normalizer_uses_search_identity_and_rejects_missing_rank():
    result = normalize_grounded_citations(
        "Acme",
        {
            "citations": [
                {"result_rank": 1, "url": "https://invented.test", "source_title": "Invented"},
                {"result_rank": 99},
                {"result_rank": "oops"},
                {"citation_position": 1},
                None,
            ]
        },
        {"results": [{"rank": 1, "url": "https://acme.test/product", "title": "Real"}]},
        owned_domains=["acme.test"],
    )
    assert len(result["citations"]) == 1
    assert result["citations"][0]["url"] == "https://acme.test/product"
    assert result["citations"][0]["source_title"] == "Real"


def test_report_endpoint_and_input_validation(client, citation_analysis):
    path = f"/api/v1/analyses/{citation_analysis.id}/citation-sources"
    response = client.get(path, params={"model": "model-b"})
    assert response.status_code == 200
    assert response.json()["rows"][0]["response_coverage"] == 100
    for params in (
        {"limit": 0},
        {"view": "invalid"},
        {"ownership": "invalid"},
        {"competitor_domains": "https://rival.test/path"},
    ):
        assert client.get(path, params=params).status_code == 422


def test_lookalike_host_is_not_owned(citation_analysis):
    response = citation_analysis.responses[0]
    audit = copy.deepcopy(response.audit)
    audit["search_results"][0]["url"] = "https://acme.test.evil.test/guide"
    response.audit = audit
    report = build_citation_report(citation_analysis)
    assert (
        next(r for r in report.rows if r.domain == "acme.test.evil.test").ownership == "third_party"
    )


def test_ambiguous_search_ranks_are_not_evidence(citation_analysis):
    response = citation_analysis.responses[0]
    audit = copy.deepcopy(response.audit)
    audit["search_results"].append({"rank": 1, "url": "https://other.test/"})
    response.audit = audit
    report = build_citation_report(citation_analysis, model="model-a", q="guide")
    assert report.rows == []


def test_live_metadata_does_not_override_a_mock_record(citation_analysis):
    for response in citation_analysis.responses:
        response.audit = {**response.audit, "measurement_mode": "mock"}
    assert build_citation_report(citation_analysis).rows == []


def test_new_runs_persist_explicit_dry_run_provenance():
    from app.pipeline.geo_run import build_geo_run

    for dry_run in (False, True):
        run = build_geo_run(
            mode="measured",
            llm_models=["model-a"],
            search_provider="tavily",
            schema_version="3.0",
            dry_run=dry_run,
        )
        assert run["dry_run"] is dry_run


def test_missing_source_record_is_not_a_successful_zero(citation_analysis):
    response = citation_analysis.responses[0]
    response.audit = {**response.audit, "search_results": None}
    report = build_citation_report(citation_analysis)
    assert report.coverage.eligible_responses == 2
    assert report.coverage.exclusion_reasons["unverified_source_record"] == 1
    assert report.rows[0].response_coverage == 50
