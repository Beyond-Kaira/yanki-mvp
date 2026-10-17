"""Standalone SERP runs API (mod-3)."""

from __future__ import annotations

import uuid

from app.db.models import Analysis, BrandContext, ModuleRun
from app.jobs.module_kinds import JOB_KIND_SERP_RUN

RUNS = "/api/v1/serp/runs"
PROFILES = "/api/v1/kyc/profiles"


def test_create_serp_run_without_queries(client, signed_in):
    signed_in()
    profile_id = client.post(
        PROFILES,
        json={"brand": "Acme Pay", "category": "money transfer", "competitors": ["Wise"]},
    ).json()["id"]

    response = client.post(
        RUNS,
        json={"brand_context_id": profile_id, "locale": "en"},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["job_kind"] == JOB_KIND_SERP_RUN
    assert body["status"] == "queued"
    assert body["payload"]["locale"] == "en"
    assert "queries" not in body["payload"] or body["payload"].get("queries") is None


def test_create_serp_run_with_explicit_queries(client, signed_in):
    signed_in()
    profile_id = client.post(
        PROFILES,
        json={"brand": "Acme Pay", "category": "money transfer"},
    ).json()["id"]

    response = client.post(
        RUNS,
        json={
            "brand_context_id": profile_id,
            "queries": ["best money transfer apps", "international remittance fees"],
        },
    )
    assert response.status_code == 202, response.text
    assert response.json()["payload"]["queries"] == [
        "best money transfer apps",
        "international remittance fees",
    ]


def test_get_serp_checks_404_until_linked(client, signed_in):
    signed_in()
    profile_id = client.post(
        PROFILES,
        json={"brand": "Acme Pay", "category": "money transfer"},
    ).json()["id"]
    run_id = client.post(RUNS, json={"brand_context_id": profile_id}).json()["id"]

    assert client.get(f"{RUNS}/{run_id}").status_code == 200
    assert client.get(f"{RUNS}/{run_id}/checks").status_code == 404


def test_get_serp_checks_from_linked_analysis(client, signed_in, db_session):
    _, org = signed_in()
    profile_id = client.post(
        PROFILES,
        json={"brand": "Acme Pay", "category": "money transfer"},
    ).json()["id"]
    run_id = client.post(RUNS, json={"brand_context_id": profile_id}).json()["id"]
    analysis = Analysis(
        url="https://acme.test/",
        kind="serp_run",
        status="done",
        org_id=org.id,
        serp_status="ok",
        serp_score=50.0,
        serp_hit_count=3,
        serp_query_count=6,
        serp_source="mock",
    )
    db_session.add(analysis)
    db_session.flush()

    run = db_session.get(ModuleRun, uuid.UUID(run_id))
    assert run is not None
    run.linked_analysis_id = analysis.id
    db_session.commit()

    checks = client.get(f"{RUNS}/{run_id}/checks")
    assert checks.status_code == 200, checks.text
    body = checks.json()
    assert body["status"] == "ok"
    assert body["score"] == 50.0
    assert body["hits"] == 3


def test_serp_run_cross_org_404(client, signed_in, db_session):
    _, org = signed_in()
    ctx = BrandContext(org_id=org.id, brand="Acme", category="fintech")
    db_session.add(ctx)
    db_session.flush()
    run = ModuleRun(
        job_kind=JOB_KIND_SERP_RUN,
        status="queued",
        org_id=org.id,
        brand_context_id=ctx.id,
        payload={},
    )
    db_session.add(run)
    db_session.commit()

    signed_in(email="other@example.test")
    assert client.get(f"{RUNS}/{run.id}").status_code == 404
    assert client.get(f"{RUNS}/{run.id}/checks").status_code == 404
