"""PATCH /analyses/{id}/kyc — guided profile edit + prompt regen."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.config import Settings
from app.db.models import Analysis, Prompt
from app.pipeline import discovery
from app.services.analysis_run_mode import RUN_MODE_GUIDED, STATUS_AWAITING_REVIEW
from app.services.guided_profile import merge_kyc_patch
from app.services.guided_review import GuidedProfileValidationError

KYC_URL = "/api/v1/analyses/{id}/kyc"


@pytest.fixture(autouse=True)
def _lift_limits():
    from app.api.main import app
    from app.config import get_settings

    app.dependency_overrides[get_settings] = lambda: Settings(
        quota_enforcement_enabled=False,
        analyses_rate_limit_per_ip_hour=1000,
        analyses_daily_cap=1000,
        user_analysis_limit=0,
    )
    yield
    app.dependency_overrides.pop(get_settings, None)


def _awaiting_guided(db_session, *, kyc: dict | None = None) -> Analysis:
    profile = kyc or {
        "company": "Acme Robotics",
        "description": "Warehouse automation",
        "industry": "Robotics",
        "category": "warehouse robots",
        "keywords": ["warehouse automation"],
        "aliases": [],
        "products": ["Acme Mover"],
        "services": [],
        "use_cases": ["warehouse automation"],
        "locations": ["Türkiye"],
        "competitors": ["Globex"],
    }
    analysis = Analysis(
        url="https://acme.test",
        status=STATUS_AWAITING_REVIEW,
        progress=45,
        run_mode=RUN_MODE_GUIDED,
        kyc=profile,
        org_id=uuid.uuid4(),
        created_by_user_id=uuid.uuid4(),
    )
    db_session.add(analysis)
    db_session.flush()
    db_session.add(
        Prompt(
            analysis_id=analysis.id,
            text="Who makes the best warehouse robots?",
            category="recommendation",
        )
    )
    db_session.commit()
    return analysis


def test_merge_kyc_patch_rejects_unknown_fields():
    with pytest.raises(GuidedProfileValidationError, match="not allowed"):
        merge_kyc_patch({"company": "Acme"}, {"unknown": "x"})


def test_patch_kyc_updates_profile_and_regenerates_prompts(client, db_session, signed_in, settings):
    user, org = signed_in()
    analysis = _awaiting_guided(db_session)
    analysis.org_id = org.id
    analysis.created_by_user_id = user.id
    db_session.commit()

    resp = client.patch(
        KYC_URL.format(id=analysis.id),
        json={"category": "industrial robots", "competitors": ["Globex", "Initech"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kyc"]["category"] == "industrial robots"
    assert body["kyc"]["competitors"] == ["Globex", "Initech"]
    assert len(body["prompts"]) == settings.prompt_count
    assert all(p["text"] for p in body["prompts"])

    db_session.expire_all()
    row = db_session.get(Analysis, analysis.id)
    prompts = db_session.scalars(select(Prompt).where(Prompt.analysis_id == analysis.id)).all()
    assert row is not None
    assert row.kyc["category"] == "industrial robots"
    assert len(prompts) == settings.prompt_count
    assert prompts[0].text != "Who makes the best warehouse robots?"


def test_patch_kyc_requires_at_least_one_field(client, db_session, signed_in):
    user, org = signed_in()
    analysis = _awaiting_guided(db_session)
    analysis.org_id = org.id
    analysis.created_by_user_id = user.id
    db_session.commit()

    assert client.patch(KYC_URL.format(id=analysis.id), json={}).status_code == 422


def test_patch_kyc_rejects_blank_company(client, db_session, signed_in):
    user, org = signed_in()
    analysis = _awaiting_guided(db_session)
    analysis.org_id = org.id
    analysis.created_by_user_id = user.id
    db_session.commit()

    resp = client.patch(KYC_URL.format(id=analysis.id), json={"company": ""})
    assert resp.status_code == 422
    assert "company" in resp.json()["detail"].lower() or "identify" in resp.json()["detail"].lower()


def test_patch_kyc_returns_409_after_measure_started(client, db_session, signed_in):
    user, org = signed_in()
    analysis = _awaiting_guided(db_session)
    analysis.org_id = org.id
    analysis.created_by_user_id = user.id
    analysis.status = "done"
    db_session.commit()

    resp = client.patch(KYC_URL.format(id=analysis.id), json={"category": "drones"})
    assert resp.status_code == 409


def test_patch_kyc_returns_409_for_quick_runs(client, db_session, signed_in):
    user, org = signed_in()
    analysis = _awaiting_guided(db_session)
    analysis.org_id = org.id
    analysis.created_by_user_id = user.id
    analysis.run_mode = "quick"
    db_session.commit()

    resp = client.patch(KYC_URL.format(id=analysis.id), json={"category": "drones"})
    assert resp.status_code == 409


def test_patch_kyc_is_404_for_other_org(client, db_session, signed_in):
    signed_in()
    analysis = _awaiting_guided(db_session)
    db_session.commit()

    resp = client.patch(KYC_URL.format(id=analysis.id), json={"category": "drones"})
    assert resp.status_code == 404


def test_patch_kyc_emits_audit_event(client, db_session, signed_in):
    from app.db.models import AuditEvent

    user, org = signed_in()
    analysis = _awaiting_guided(db_session)
    analysis.org_id = org.id
    analysis.created_by_user_id = user.id
    db_session.commit()

    resp = client.patch(KYC_URL.format(id=analysis.id), json={"category": "AMRs"})
    assert resp.status_code == 200

    db_session.expire_all()
    events = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.action == "analysis:kyc_patch",
            AuditEvent.entity_id == analysis.id,
        )
    ).all()
    assert len(events) == 1
    assert events[0].actor_id == user.id


def test_end_to_end_guided_pause_then_patch(client, db_session, signed_in, settings, monkeypatch):
    user, org = signed_in()
    monkeypatch.setattr(
        discovery,
        "discover_detailed",
        lambda url: discovery.CrawlResult(text="Acme builds warehouse robots and tools."),
    )

    submit = client.post(
        "/api/v1/analyses",
        json={"url": "https://acme.test", "mode": "guided"},
    )
    assert submit.status_code == 202
    analysis_id = uuid.UUID(submit.json()["id"])
    row = db_session.get(Analysis, analysis_id)
    row.status = "running"
    db_session.commit()

    from app.pipeline import runner

    runner.run_pipeline(db_session, analysis_id, settings)
    db_session.expire_all()
    paused = db_session.get(Analysis, analysis_id)
    assert paused.status == STATUS_AWAITING_REVIEW

    before = client.get(f"/api/v1/analyses/{analysis_id}/prompts").json()["prompts"]
    patched = client.patch(
        KYC_URL.format(id=analysis_id),
        json={"category": "mobile robots"},
    )
    assert patched.status_code == 200
    after = patched.json()["prompts"]
    assert after != before
    assert patched.json()["kyc"]["category"] == "mobile robots"
