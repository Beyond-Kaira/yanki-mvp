"""Interim per-user analysis stock limit (hardcoded, no env)."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import Analysis
from app.services.user_analysis_limits import USER_ANALYSIS_LIMIT

ANALYSES_URL = "/api/v1/analyses"
VALID_URL = "https://acme.test"


@pytest.fixture(autouse=True)
def isolated_limits():
    """User limit is what this file tests — lift org quota and IP burst."""

    app.dependency_overrides[get_settings] = lambda: Settings(
        quota_enforcement_enabled=False,
        analyses_rate_limit_per_ip_hour=1000,
        analyses_daily_cap=1000,
    )
    yield
    app.dependency_overrides.pop(get_settings, None)


def _submit(client, url: str = VALID_URL):
    return client.post(ANALYSES_URL, json={"url": url})


def test_user_may_hold_five_analyses_and_the_sixth_is_refused(
    client, db_session, signed_in
) -> None:
    user, _org = signed_in()

    for n in range(USER_ANALYSIS_LIMIT):
        assert _submit(client).status_code == 202, f"submit {n + 1}"

    refused = _submit(client)
    assert refused.status_code == 429
    body = refused.json()
    assert body["metric"] == "user_analyses"
    assert body["limit"] == USER_ANALYSIS_LIMIT
    assert body["used"] == USER_ANALYSIS_LIMIT

    assert (
        db_session.scalar(sa.select(sa.func.count()).select_from(Analysis)) == USER_ANALYSIS_LIMIT
    )
    rows = db_session.scalars(
        sa.select(Analysis).where(Analysis.created_by_user_id == user.id)
    ).all()
    assert len(rows) == USER_ANALYSIS_LIMIT


def test_failed_analyses_do_not_count_toward_the_user_limit(client, db_session, signed_in) -> None:
    user, org = signed_in()
    for index in range(USER_ANALYSIS_LIMIT):
        db_session.add(
            Analysis(
                url=f"https://failed-{index}.test",
                org_id=org.id,
                created_by_user_id=user.id,
                status="failed",
            )
        )
    db_session.commit()

    for n in range(USER_ANALYSIS_LIMIT):
        assert _submit(client).status_code == 202, f"submit {n + 1}"

    assert _submit(client).status_code == 429


def test_legacy_rows_without_created_by_user_id_do_not_count(client, db_session, signed_in) -> None:
    _user, org = signed_in()
    for index in range(USER_ANALYSIS_LIMIT):
        db_session.add(
            Analysis(
                url=f"https://legacy-{index}.test",
                org_id=org.id,
                created_by_user_id=None,
                status="done",
            )
        )
    db_session.commit()

    for n in range(USER_ANALYSIS_LIMIT):
        assert _submit(client).status_code == 202, f"submit {n + 1}"

    assert _submit(client).status_code == 429
