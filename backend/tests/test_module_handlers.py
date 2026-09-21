"""Standalone module run handlers (mod-6)."""

from __future__ import annotations

import uuid

import pytest

from app.db.models import BrandContext, ModuleRun
from app.jobs.module_kinds import JOB_KIND_GEO_RUN, JOB_KIND_KYC_EXTRACT, JOB_KIND_SERP_RUN
from app.pipeline import discovery
from app.pipeline.discovery import CrawlResult
from app.pipeline.module_handlers import ModuleRunError, run_module_run
from app.services.module_runs import enqueue_module_run


@pytest.fixture
def brand_context(db_session, signed_in):
    _, org = signed_in()
    ctx = BrandContext(
        org_id=org.id,
        brand="Acme Pay",
        category="money transfer",
        profile={
            "company": "Acme Pay",
            "category": "money transfer",
            "competitors": ["Wise"],
        },
    )
    db_session.add(ctx)
    db_session.commit()
    return ctx


def test_kyc_extract_updates_profile(db_session, brand_context, settings, monkeypatch):
    def fake_discover(_url: str) -> CrawlResult:
        return CrawlResult(text="Acme Pay international remittance platform.")

    monkeypatch.setattr(discovery, "discover_detailed", fake_discover)
    monkeypatch.setattr(
        "app.pipeline.module_handlers.is_public_url",
        lambda url: ".test" in url,
    )

    run = ModuleRun(
        job_kind=JOB_KIND_KYC_EXTRACT,
        status="running",
        brand_context_id=brand_context.id,
        org_id=brand_context.org_id,
        payload={"source_url": "https://acme.test/"},
    )
    db_session.add(run)
    db_session.commit()

    finished = run_module_run(db_session, run.id, settings)
    assert finished.status == "done"
    assert finished.result["brand"] == brand_context.brand
    db_session.refresh(brand_context)
    assert brand_context.source_url == "https://acme.test/"
    assert brand_context.profile is not None


def test_kyc_extract_requires_source_url(db_session, brand_context, settings):
    run = ModuleRun(
        job_kind=JOB_KIND_KYC_EXTRACT,
        status="running",
        brand_context_id=brand_context.id,
        org_id=brand_context.org_id,
        payload={},
    )
    db_session.add(run)
    db_session.commit()

    with pytest.raises(ModuleRunError):
        run_module_run(db_session, run.id, settings)
    db_session.refresh(run)
    assert run.status == "failed"


def test_geo_run_requires_prompts(db_session, brand_context, settings):
    run = ModuleRun(
        job_kind=JOB_KIND_GEO_RUN,
        status="running",
        brand_context_id=brand_context.id,
        org_id=brand_context.org_id,
        payload={},
    )
    db_session.add(run)
    db_session.commit()

    with pytest.raises(ModuleRunError):
        run_module_run(db_session, run.id, settings)
    db_session.refresh(run)
    assert run.status == "failed"


def test_serp_run_without_source_marks_unavailable(db_session, brand_context, settings, monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.module_handlers.serp_registry.get_serp_source",
        lambda _settings: None,
    )

    run = ModuleRun(
        job_kind=JOB_KIND_SERP_RUN,
        status="running",
        brand_context_id=brand_context.id,
        org_id=brand_context.org_id,
        payload={},
    )
    db_session.add(run)
    db_session.commit()

    finished = run_module_run(db_session, run.id, settings)
    assert finished.status == "done"
    assert finished.result["reason"] == "no serp source configured"
    assert finished.linked_analysis_id is not None


def test_enqueue_module_run_validates_org(db_session, signed_in):
    user, org = signed_in()
    other_org = uuid.uuid4()
    ctx = BrandContext(org_id=other_org, brand="Other")
    db_session.add(ctx)
    db_session.commit()

    from app.services.module_runs import ModuleRunValidationError, enqueue_module_run

    with pytest.raises(ModuleRunValidationError):
        enqueue_module_run(
            db_session,
            job_kind=JOB_KIND_KYC_EXTRACT,
            org_id=org.id,
            user_id=user.id,
            brand_context_id=ctx.id,
        )
