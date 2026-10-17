"""AI visibility standalone runs API (mod-4)."""

from __future__ import annotations

import uuid

from app.db.models import BrandContext, ModuleRun
from app.jobs.module_kinds import JOB_KIND_GEO_RUN, JOB_KIND_KYC_EXTRACT

RUNS = "/api/v1/ai-visibility/runs"
PROFILES = "/api/v1/kyc/profiles"


def _profile(client, signed_in):
    signed_in()
    body = client.post(
        PROFILES,
        json={"brand": "Acme Pay", "category": "money transfer", "competitors": ["Wise"]},
    ).json()
    return body["id"]


def test_create_run_returns_202_and_queued_module_run(client, signed_in):
    profile_id = _profile(client, signed_in)
    response = client.post(
        RUNS,
        json={
            "brand_context_id": profile_id,
            "prompts": [{"text": "Best remittance apps?", "category": "general"}],
            "mode": "simulated",
        },
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["job_kind"] == JOB_KIND_GEO_RUN
    assert body["status"] == "queued"
    assert body["brand_context_id"] == profile_id
    assert body["payload"]["mode"] == "simulated"


def test_get_run_and_geo_404_until_linked(client, signed_in, db_session):
    profile_id = _profile(client, signed_in)
    created = client.post(
        RUNS,
        json={
            "brand_context_id": profile_id,
            "prompts": [{"text": "Who leads in fintech?"}],
        },
    ).json()
    run_id = created["id"]

    poll = client.get(f"{RUNS}/{run_id}")
    assert poll.status_code == 200
    assert poll.json()["id"] == run_id

    geo = client.get(f"{RUNS}/{run_id}/geo")
    assert geo.status_code == 404

    run = db_session.get(ModuleRun, uuid.UUID(run_id))
    assert run is not None
    run.linked_analysis_id = uuid.uuid4()
    db_session.commit()

    geo_missing = client.get(f"{RUNS}/{run_id}/geo")
    assert geo_missing.status_code == 404


def test_cross_org_run_is_404(client, signed_in):
    signed_in()
    profile_id = client.post(
        PROFILES,
        json={"brand": "Alpha", "category": "saas"},
    ).json()["id"]
    run_id = client.post(
        RUNS,
        json={
            "brand_context_id": profile_id,
            "prompts": [{"text": "Top CRM tools?"}],
        },
    ).json()["id"]

    signed_in(email="other@example.com")
    assert client.get(f"{RUNS}/{run_id}").status_code == 404
    assert client.get(f"{RUNS}/{run_id}/geo").status_code == 404


def test_non_geo_module_run_not_visible_on_ai_visibility_route(client, signed_in, db_session):
    _, org = signed_in()
    ctx = BrandContext(org_id=org.id, brand="Acme", category="fintech", profile={"company": "Acme"})
    db_session.add(ctx)
    db_session.flush()
    run = ModuleRun(
        job_kind=JOB_KIND_KYC_EXTRACT,
        status="queued",
        org_id=org.id,
        brand_context_id=ctx.id,
        payload={},
    )
    db_session.add(run)
    db_session.commit()

    assert client.get(f"{RUNS}/{run.id}").status_code == 404
