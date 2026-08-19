"""PATCH /analyses/{id}/prompts — guided prompt curation."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.config import Settings
from app.db.models import Analysis, AuditEvent, Prompt
from app.services.analysis_run_mode import RUN_MODE_GUIDED, STATUS_AWAITING_REVIEW
from app.services.guided_prompts import (
    PROMPT_SOURCE_EDITED,
    PROMPT_SOURCE_GENERATED,
    PROMPT_SOURCE_USER,
)

PROMPTS_URL = "/api/v1/analyses/{id}/prompts"


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


def _awaiting_with_prompts(db_session, user_id, org_id, *, settings) -> Analysis:
    analysis = Analysis(
        url="https://acme.test",
        status=STATUS_AWAITING_REVIEW,
        progress=45,
        run_mode=RUN_MODE_GUIDED,
        org_id=org_id,
        created_by_user_id=user_id,
        kyc={
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
        },
    )
    db_session.add(analysis)
    db_session.flush()
    for index in range(settings.prompt_count):
        db_session.add(
            Prompt(
                analysis_id=analysis.id,
                text=f"What are the best warehouse robots option {index}?",
                category="recommendation",
                source=PROMPT_SOURCE_GENERATED,
                locked=False,
            )
        )
    db_session.commit()
    db_session.refresh(analysis)
    return analysis


def test_patch_prompts_edits_generated_and_adds_custom(client, db_session, signed_in, settings):
    user, org = signed_in()
    analysis = _awaiting_with_prompts(db_session, user.id, org.id, settings=settings)
    prompts = list(analysis.prompts)
    keep = prompts[:2]
    body = {
        "prompts": [
            {"id": str(keep[0].id), "text": keep[0].text, "category": keep[0].category},
            {
                "id": str(keep[1].id),
                "text": "Which vendors lead the AMR market in Europe?",
                "category": "makers",
            },
            {
                "text": "How do integrators compare warehouse automation vendors?",
                "category": "custom",
            },
        ]
    }

    resp = client.patch(PROMPTS_URL.format(id=analysis.id), json=body)
    assert resp.status_code == 200, resp.text
    payload = resp.json()["prompts"]
    assert len(payload) == 3
    assert payload[0]["source"] == PROMPT_SOURCE_GENERATED
    assert payload[1]["source"] == PROMPT_SOURCE_EDITED
    assert payload[2]["source"] == PROMPT_SOURCE_USER
    assert all(p["editable"] is True for p in payload)

    db_session.expire_all()
    rows = db_session.scalars(select(Prompt).where(Prompt.analysis_id == analysis.id)).all()
    assert len(rows) == 3


def test_patch_prompts_rejects_brand_leak_in_category_prompt(
    client, db_session, signed_in, settings
):
    user, org = signed_in()
    analysis = _awaiting_with_prompts(db_session, user.id, org.id, settings=settings)
    prompt = analysis.prompts[0]
    resp = client.patch(
        PROMPTS_URL.format(id=analysis.id),
        json={
            "prompts": [
                {
                    "id": str(prompt.id),
                    "text": "What are the best Acme Robotics warehouse options?",
                    "category": "recommendation",
                }
            ]
        },
    )
    assert resp.status_code == 422


def test_patch_prompts_rejects_more_than_three_new_prompts(client, db_session, signed_in, settings):
    user, org = signed_in()
    analysis = _awaiting_with_prompts(db_session, user.id, org.id, settings=settings)
    resp = client.patch(
        PROMPTS_URL.format(id=analysis.id),
        json={
            "prompts": [
                {"text": f"Custom question {index}?", "category": "custom"} for index in range(4)
            ]
        },
    )
    assert resp.status_code == 422


def test_patch_prompts_locked_row_must_be_included_unchanged(
    client, db_session, signed_in, settings
):
    user, org = signed_in()
    analysis = _awaiting_with_prompts(db_session, user.id, org.id, settings=settings)
    locked = analysis.prompts[0]
    locked.locked = True
    db_session.commit()

    resp = client.patch(
        PROMPTS_URL.format(id=analysis.id),
        json={
            "prompts": [
                {
                    "id": str(analysis.prompts[1].id),
                    "text": analysis.prompts[1].text,
                    "category": analysis.prompts[1].category,
                }
            ]
        },
    )
    assert resp.status_code == 422
    assert "locked" in resp.json()["detail"].lower()

    ok = client.patch(
        PROMPTS_URL.format(id=analysis.id),
        json={
            "prompts": [
                {
                    "id": str(locked.id),
                    "text": locked.text,
                    "category": locked.category,
                },
                {
                    "id": str(analysis.prompts[1].id),
                    "text": analysis.prompts[1].text,
                    "category": analysis.prompts[1].category,
                },
            ]
        },
    )
    assert ok.status_code == 200


def test_patch_prompts_returns_409_when_not_awaiting_review(
    client, db_session, signed_in, settings
):
    user, org = signed_in()
    analysis = _awaiting_with_prompts(db_session, user.id, org.id, settings=settings)
    analysis.status = "done"
    db_session.commit()

    resp = client.patch(
        PROMPTS_URL.format(id=analysis.id),
        json={
            "prompts": [
                {"text": "Who leads the market?", "category": "custom"},
            ]
        },
    )
    assert resp.status_code == 409


def test_patch_prompts_emits_audit_event(client, db_session, signed_in, settings):
    user, org = signed_in()
    analysis = _awaiting_with_prompts(db_session, user.id, org.id, settings=settings)
    prompt = analysis.prompts[0]

    resp = client.patch(
        PROMPTS_URL.format(id=analysis.id),
        json={
            "prompts": [
                {
                    "id": str(prompt.id),
                    "text": "Who are strong AMR vendors?",
                    "category": "makers",
                }
            ]
        },
    )
    assert resp.status_code == 200

    db_session.expire_all()
    events = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.action == "analysis:prompts_patch",
            AuditEvent.entity_id == analysis.id,
        )
    ).all()
    assert len(events) == 1
    assert events[0].after["prompts"][0]["source"] == PROMPT_SOURCE_EDITED
