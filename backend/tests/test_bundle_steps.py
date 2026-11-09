"""Thin bundle orchestrator flags (mod-8)."""

from __future__ import annotations

from app.db.models import Analysis, BrandContext
from app.pipeline.runner import run_pipeline
from app.services.bundle_steps import BundleSteps, bundle_steps_from_analysis


def test_bundle_steps_from_analysis_defaults():
    analysis = Analysis(url="https://x.test", bundle_steps=None)
    steps = bundle_steps_from_analysis(analysis)
    assert steps.kyc and steps.geo and steps.serp


def test_run_pipeline_skips_geo_when_disabled(db_session, settings, monkeypatch):
    ctx = BrandContext(brand="Skip Geo Co", profile={"company": "Skip Geo Co", "category": "saas"})
    db_session.add(ctx)
    db_session.flush()

    analysis = Analysis(
        url="https://skipgeo.test",
        brand_context_id=ctx.id,
        bundle_steps=BundleSteps(kyc=False, geo=False, serp=False).model_dump(),
        status="queued",
    )
    db_session.add(analysis)
    db_session.commit()

    monkeypatch.setattr("app.pipeline.runner.discovery.discover_detailed", lambda url: type("C", (), {"text": "Acme site copy"})())
    monkeypatch.setattr(
        "app.pipeline.runner.prompts_step.generate_prompts",
        lambda kyc, count: [type("S", (), {"text": "q", "category": "c"})()],
    )

    finished = run_pipeline(db_session, analysis.id, settings)
    assert finished.status == "done"
    assert finished.progress == 45
    assert finished.geo_score is None
