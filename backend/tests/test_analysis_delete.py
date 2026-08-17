"""DELETE /api/v1/analyses/{id} — owner-only manual delete for done runs (P4)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import Analysis, Prompt
from app.services.user_analysis_limits import USER_ANALYSIS_LIMIT

VALID_URL = "https://acme.test"


@pytest.fixture(autouse=True)
def unmetered():
    app.dependency_overrides[get_settings] = lambda: Settings(
        analyses_rate_limit_per_ip_hour=1000,
        analyses_daily_cap=1000,
        quota_enforcement_enabled=False,
    )
    yield
    app.dependency_overrides.pop(get_settings, None)


def _submit(client):
    return client.post("/api/v1/analyses", json={"url": VALID_URL})


def _seed_done(
    session: Session,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    count: int = 1,
) -> list[Analysis]:
    rows = []
    for index in range(count):
        row = Analysis(
            url=f"https://acme.test/{index}",
            org_id=org_id,
            created_by_user_id=user_id,
            status="done",
            geo_score=42.0,
        )
        session.add(row)
        rows.append(row)
    session.commit()
    return rows


def test_owner_may_delete_a_done_analysis(client, db_session, signed_in) -> None:
    user, org = signed_in()
    rows = _seed_done(db_session, org_id=org.id, user_id=user.id)
    analysis_id = rows[0].id

    response = client.delete(f"/api/v1/analyses/{analysis_id}")

    assert response.status_code == 204, response.text
    db_session.expire_all()
    assert db_session.get(Analysis, analysis_id) is None


def test_deleting_a_done_analysis_frees_a_stock_slot(client, db_session, signed_in) -> None:
    user, org = signed_in()
    rows = _seed_done(db_session, org_id=org.id, user_id=user.id, count=USER_ANALYSIS_LIMIT)
    to_delete = rows[0].id

    assert client.delete(f"/api/v1/analyses/{to_delete}").status_code == 204
    assert _submit(client).status_code == 202


def test_list_reports_freed_active_slot_after_delete(client, db_session, signed_in) -> None:
    user, org = signed_in()
    rows = _seed_done(db_session, org_id=org.id, user_id=user.id, count=USER_ANALYSIS_LIMIT)

    before = client.get("/api/v1/analyses").json()
    assert before["user_analyses_used"] == USER_ANALYSIS_LIMIT

    assert client.delete(f"/api/v1/analyses/{rows[0].id}").status_code == 204

    after = client.get("/api/v1/analyses").json()
    assert after["user_analyses_used"] == USER_ANALYSIS_LIMIT - 1


def test_another_users_done_analysis_returns_404(client, db_session, signed_in) -> None:
    from app.db.models import Membership, User
    from app.services.auth import hash_password

    owner, org = signed_in(email="owner@example.test")
    teammate = User(email="teammate@example.test", password_hash=hash_password("correct-horse"))
    db_session.add(teammate)
    db_session.flush()
    db_session.add(
        Membership(org_id=org.id, user_id=teammate.id, role="viewer", status="active")
    )
    rows = _seed_done(db_session, org_id=org.id, user_id=teammate.id)
    theirs = rows[0].id

    assert client.delete(f"/api/v1/analyses/{theirs}").status_code == 404
    assert db_session.get(Analysis, theirs) is not None


@pytest.mark.parametrize("status", ["queued", "running"])
def test_in_flight_analyses_cannot_be_deleted(client, db_session, signed_in, status) -> None:
    user, org = signed_in()
    row = Analysis(
        url=VALID_URL,
        org_id=org.id,
        created_by_user_id=user.id,
        status=status,
    )
    db_session.add(row)
    db_session.commit()

    response = client.delete(f"/api/v1/analyses/{row.id}")

    assert response.status_code == 409, response.text
    assert db_session.get(Analysis, row.id) is not None


def test_delete_cascades_to_child_rows(client, db_session, signed_in) -> None:
    from sqlalchemy import func, select

    user, org = signed_in()
    row = Analysis(
        url=VALID_URL,
        org_id=org.id,
        created_by_user_id=user.id,
        status="done",
    )
    db_session.add(row)
    db_session.flush()
    db_session.add(Prompt(analysis_id=row.id, text="hello", category="brand"))
    db_session.commit()
    analysis_id = row.id

    assert client.delete(f"/api/v1/analyses/{analysis_id}").status_code == 204

    db_session.expire_all()
    assert db_session.get(Analysis, analysis_id) is None
    assert (
        db_session.scalar(
            select(func.count()).select_from(Prompt).where(Prompt.analysis_id == analysis_id)
        )
        == 0
    )
