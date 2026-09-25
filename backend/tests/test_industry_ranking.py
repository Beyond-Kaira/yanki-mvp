"""Sector-driven global aggregates, evidence validation and output boundaries."""

import uuid

import pytest
from sqlalchemy import event

from app.db.models import GeoRecord, Prompt, Response
from app.industry_citations.ranking import build_industry_ranking


@pytest.fixture
def record_factory(db_session, make_analysis):
    def create(
        *,
        sector="e-commerce",
        question="Which shops?",
        group="recommendation",
        live=True,
        model="model-a",
        answer="Sources [1, 2].",
        error=False,
        citations=None,
        status="done",
    ):
        analysis = make_analysis(
            status=status,
            org_id=uuid.uuid4(),
            geo_run={
                "mode": "measured",
                "dry_run": False if live else None,
                "search": {"provider": "tavily"},
            },
        )
        prompt = Prompt(analysis_id=analysis.id, text=question, category=group)
        db_session.add(prompt)
        db_session.flush()
        response = Response(
            analysis_id=analysis.id,
            prompt_id=prompt.id,
            llm_provider="openrouter",
            model=model,
            raw_text="PRIVATE raw text",
            audit={"measurement_mode": "measured"},
        )
        db_session.add(response)
        db_session.flush()
        record = GeoRecord(
            analysis_id=analysis.id,
            response_id=response.id,
            brand="PRIVATE BRAND",
            sector=sector,
            prompt=question,
            prompt_group=group,
            grounded_answer=answer,
            error=error,
            search_results=[
                {"rank": 1, "url": "https://source.test/a?utm_source=test", "title": "PRIVATE"},
                {"rank": 2, "url": "https://source.test/b", "title": "PRIVATE"},
            ],
            citations=citations
            if citations is not None
            else [{"result_rank": 1}, {"result_rank": 1}, {"result_rank": 2}],
        )
        db_session.add(record)
        db_session.flush()
        return record

    return create


def test_cross_org_response_union_and_distinct_questions(db_session, record_factory):
    record_factory(question="Which shops?")
    record_factory(question="  WHICH   shops? ", model="model-b")
    record_factory(question="Other question?", answer="No sources", citations=[])
    report = build_industry_ranking(db_session, " E commerce ")
    assert report.candidate_responses == report.eligible_responses == 3
    assert report.distinct_questions == 2
    assert report.site_count == 1 and report.page_count == 2
    site = report.sites[0]
    assert site.response_count == 2  # not 4 pages or 6 repeated citations
    assert site.question_count == 1
    assert site.response_coverage == 66.67
    assert site.model_counts == {"model-a": 1, "model-b": 1}
    assert all(page.response_count == 2 for page in site.pages)
    assert site.pages[0].url == "https://source.test/a"


def test_sector_label_is_used_without_reclassifying_question(db_session, record_factory):
    record_factory(question="Which cosmetics?", sector="e-commerce")
    record_factory(question="Which online shops?", sector="financial technology")
    record_factory(group="brand-probe")
    record_factory(live=False)
    report = build_industry_ranking(db_session, "ecommerce")
    assert report.candidate_responses == 3
    assert report.eligible_responses == 1
    assert report.excluded_responses == {"brand_probe": 1, "unknown_provenance": 1}


def test_ranking_filters_by_sector_key_in_sql(db_session, record_factory):
    record_factory(sector="e-commerce")
    record_factory(sector="artificial intelligence")
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", capture)
    try:
        report = build_industry_ranking(db_session, "ecommerce")
    finally:
        event.remove(db_session.bind, "before_cursor_execute", capture)

    assert report.candidate_responses == 1
    ranking_selects = [
        statement
        for statement in statements
        if "FROM geo_records" in statement and "JOIN responses" in statement
    ]
    assert len(ranking_selects) == 1
    assert "geo_records.sector_key =" in ranking_selects[0]


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"error": True}, "failed_or_missing_answer"),
        ({"answer": " "}, "failed_or_missing_answer"),
        ({"model": "mock"}, "mock_or_simulated"),
        ({"status": "failed"}, "analysis_not_complete"),
    ],
)
def test_exclusions(db_session, record_factory, kwargs, reason):
    record_factory(**kwargs)
    report = build_industry_ranking(db_session, "e-commerce")
    assert report.excluded_responses == {reason: 1}
    assert report.eligible_responses == 0 and report.sites == []


def test_rejected_citations_do_not_remove_successful_answer_from_denominator(
    db_session,
    record_factory,
):
    record_factory(
        answer="Source [1].",
        citations=[
            {"result_rank": 1, "url": "https://invented.test"},
            {"result_rank": 2},
            {"result_rank": 9},
            {"result_rank": True},
            "bad",
        ],
    )
    report = build_industry_ranking(db_session, "e-commerce")
    assert report.eligible_responses == 1
    assert report.sites == []
    assert report.rejected_citations == {
        "source_url_mismatch": 1,
        "missing_inline_marker": 1,
        "unmatched_result_rank": 1,
        "invalid_result_rank": 1,
        "malformed_citation": 1,
    }


def test_no_customer_text_or_identifiers_in_output(db_session, record_factory):
    record = record_factory(question="PRIVATE QUESTION", answer="PRIVATE ANSWER [1]")
    report = build_industry_ranking(db_session, "e-commerce")
    output = report.model_dump_json()
    assert "PRIVATE" not in output
    for identifier in [record.id, record.response_id, record.analysis_id]:
        assert str(identifier) not in output


def test_empty_sector_has_empty_report_and_invalid_input_is_rejected(db_session):
    report = build_industry_ranking(db_session, "unknown industry")
    assert report.candidate_responses == 0 and report.sites == []
    with pytest.raises(ValueError):
        build_industry_ranking(db_session, "  ")


def test_global_api_requires_login(client):
    assert client.get("/api/v1/industry-citations/sectors").status_code == 401
    assert client.get("/api/v1/industry-citations/ranking?sector=e-commerce").status_code == 401


def test_catalog_and_ranking_api_across_orgs(client, signed_in, record_factory, db_session):
    signed_in()
    record_factory(sector=" ECOMMERCE ")
    record_factory(sector="e-commerce", model="model-b")
    record_factory(sector="Artificial Intelligence", live=False)
    db_session.commit()
    catalog = client.get("/api/v1/industry-citations/sectors")
    assert catalog.status_code == 200
    assert catalog.json() == [
        {"sector": "artificial intelligence", "record_count": 1},
        {"sector": "e-commerce", "record_count": 2},
    ]
    result = client.get("/api/v1/industry-citations/ranking?sector=ecommerce&limit=1")
    assert result.status_code == 200
    report = result.json()
    assert report["eligible_responses"] == 2
    assert report["sites"][0]["response_count"] == 2
    assert report["limit"] == 1
    assert "PRIVATE" not in result.text
    assert "analysis_id" not in result.text
    assert "response_id" not in result.text
    empty = client.get("/api/v1/industry-citations/ranking?sector=artificial%20intelligence").json()
    assert empty["candidate_responses"] == 1 and empty["eligible_responses"] == 0
    page = client.get("/api/v1/industry-citations/ranking?sector=e-commerce&offset=1").json()
    assert page["sites"] == [] and page["site_count"] == 1
    assert page["eligible_responses"] == 2


@pytest.mark.parametrize(
    "query", ["sector=%20", "sector=e-commerce&limit=101", "sector=e-commerce&offset=-1", ""]
)
def test_ranking_api_rejects_invalid_queries(client, signed_in, query):
    signed_in()
    assert client.get("/api/v1/industry-citations/ranking?" + query).status_code == 422
