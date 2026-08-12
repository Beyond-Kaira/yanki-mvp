"""Additive GET slices for analyses (phase 1 of analysis API split)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.db.models import Prompt, Response, SeoCheck, SerpCheck


@pytest.fixture()
def done_analysis(db_session, make_analysis):
    analysis = make_analysis(
        url="https://acme.test",
        status="done",
        progress=100,
        kyc={"company": "Acme", "industry": "Robotics", "category": "warehouse robots"},
        geo_score=72.5,
        footprint_count=1,
        total_responses=1,
        reliability_score=0.9,
        interventions=[{"id": "fix-meta", "title": "Improve meta"}],
        citation_summary={"cite_rate": 0.4},
        serp_status="ok",
        serp_source="searxng",
        serp_score=0.33,
        serp_hit_count=2,
        serp_query_count=6,
        seo_status="ok",
        seo_score=97.8,
        seo_grade="A",
    )
    prompt = Prompt(
        analysis_id=analysis.id,
        text="Best warehouse robots?",
        category="recommendation",
    )
    db_session.add(prompt)
    db_session.flush()
    db_session.add(
        Response(
            analysis_id=analysis.id,
            prompt_id=prompt.id,
            engine="measured",
            model="gpt-test",
            raw_text="Acme is strong.",
            footprint=True,
            matched_snippet="Acme",
            cost_usd=Decimal("0.001"),
            audit={"mentioned": True},
        )
    )
    db_session.add(
        SerpCheck(
            analysis_id=analysis.id,
            query="best warehouse robots",
            source="searxng",
            hit=True,
            rank=3,
            matched_url="https://acme.test",
            matched_snippet="Acme robots",
            matched_via="title",
            result_count=10,
        )
    )
    db_session.add(
        SeoCheck(
            analysis_id=analysis.id,
            check_id="robots_txt",
            title="Robots.txt",
            severity="critical",
            status="pass",
            detail="Allows crawlers",
            evidence="User-agent: *",
        )
    )
    db_session.commit()
    return analysis


def test_slice_routes_return_404_for_unknown_id(client):
    missing = uuid.uuid4()
    for path in ("/kyc", "/prompts", "/geo", "/serp", "/seo"):
        resp = client.get(f"/api/v1/analyses/{missing}{path}")
        assert resp.status_code == 404, path


def test_kyc_slice_returns_stored_profile(client, done_analysis):
    slice_body = client.get(f"/api/v1/analyses/{done_analysis.id}/kyc").json()
    assert slice_body["kyc"]["company"] == "Acme"
    assert slice_body["kyc"]["category"] == "warehouse robots"


def test_prompts_slice_returns_generated_rows(client, done_analysis):
    slice_body = client.get(f"/api/v1/analyses/{done_analysis.id}/prompts").json()
    assert len(slice_body["prompts"]) == 1
    assert slice_body["prompts"][0]["text"] == "Best warehouse robots?"


def test_geo_slice_returns_measured_payload(client, done_analysis):
    geo = client.get(f"/api/v1/analyses/{done_analysis.id}/geo").json()
    assert geo["geo_score"] == 72.5
    assert geo["footprint_count"] == 1
    assert len(geo["responses"]) == 1
    assert geo["responses"][0]["engine"] == "measured"
    assert geo["interventions"][0]["id"] == "fix-meta"


def test_serp_slice_returns_checks(client, done_analysis):
    serp = client.get(f"/api/v1/analyses/{done_analysis.id}/serp").json()
    assert serp["status"] == "ok"
    assert serp["checks"][0]["query"] == "best warehouse robots"


def test_seo_slice_returns_checks(client, done_analysis):
    seo = client.get(f"/api/v1/analyses/{done_analysis.id}/seo").json()
    assert seo["grade"] == "A"
    assert seo["checks"][0]["check_id"] == "robots_txt"


def test_serp_and_seo_slices_are_null_when_not_measured(client, make_analysis):
    analysis = make_analysis()
    assert client.get(f"/api/v1/analyses/{analysis.id}/serp").json() is None
    assert client.get(f"/api/v1/analyses/{analysis.id}/seo").json() is None


def test_main_get_is_thin_after_slice_routes(client, make_analysis):
    """Regression: poll envelope has summary columns only."""
    analysis = make_analysis(url="https://example.test")

    body = client.get(f"/api/v1/analyses/{analysis.id}").json()
    assert "result" not in body
    assert body["geo_score"] is None
    assert client.get(f"/api/v1/analyses/{analysis.id}/serp").json() is None
    assert client.get(f"/api/v1/analyses/{analysis.id}/seo").json() is None
