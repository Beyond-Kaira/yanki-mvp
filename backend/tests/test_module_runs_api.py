"""Shared GET /api/v1/module/runs/{id} (items 16–17)."""

from __future__ import annotations

import uuid

from app.db.models import BrandContext, ModuleRun
from app.jobs.module_kinds import JOB_KIND_GEO_RUN, JOB_KIND_KYC_EXTRACT

MODULE_RUNS = "/api/v1/module/runs"
PROFILES = "/api/v1/kyc/profiles"


def test_get_module_run_after_extract_enqueue(client, signed_in):
    signed_in()
    profile_id = client.post(
        PROFILES,
        json={"brand": "Acme Pay", "category": "money transfer", "domain": "acme.test"},
    ).json()["id"]

    enqueued = client.post(
        f"{PROFILES}/{profile_id}/extract",
        json={"source_url": "https://acme.test/"},
    ).json()

    poll = client.get(f"{MODULE_RUNS}/{enqueued['id']}")
    assert poll.status_code == 200, poll.text
    body = poll.json()
    assert body["id"] == enqueued["id"]
    assert body["job_kind"] == JOB_KIND_KYC_EXTRACT
    assert body["status"] == "queued"
    assert body["brand_context_id"] == profile_id
    assert body["attempts"] == 0
    assert body["created_by_user_id"] is not None


def test_get_module_run_cross_org_404(client, signed_in, db_session):
    _, org = signed_in()
    ctx = BrandContext(org_id=org.id, brand="Acme", category="fintech")
    db_session.add(ctx)
    db_session.flush()
    run = ModuleRun(
        job_kind=JOB_KIND_GEO_RUN,
        status="queued",
        org_id=org.id,
        brand_context_id=ctx.id,
        payload={},
    )
    db_session.add(run)
    db_session.commit()

    signed_in(email="other@example.test")
    assert client.get(f"{MODULE_RUNS}/{run.id}").status_code == 404


def test_get_module_run_unknown_id_404(client, signed_in):
    signed_in()
    assert client.get(f"{MODULE_RUNS}/{uuid.uuid4()}").status_code == 404
