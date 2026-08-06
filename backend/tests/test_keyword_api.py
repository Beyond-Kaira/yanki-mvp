"""Keyword Research preview HTTP surface."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.auth_dependencies import get_current_user
from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import User


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def enabled_dry_run_settings() -> Iterator[Settings]:
    settings = Settings(keyword_enabled=True, dry_run=True, keyword_max_ideas=20)
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture()
def authed_user() -> Iterator[User]:
    fake = User(email="keyword-tester@example.com", password_hash="x")

    def _user() -> User:
        return fake

    app.dependency_overrides[get_current_user] = _user
    yield fake
    app.dependency_overrides.pop(get_current_user, None)


def test_keywords_dark_when_flag_off(client: TestClient, authed_user: User) -> None:
    settings = Settings(keyword_enabled=False, dry_run=True)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = client.post(
            "/api/v1/keywords/expand",
            json={"seed": "money transfer", "locale": "en"},
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_expand_requires_auth(
    client: TestClient, enabled_dry_run_settings: Settings
) -> None:
    response = client.post(
        "/api/v1/keywords/expand",
        json={"seed": "money transfer", "locale": "en"},
    )
    assert response.status_code == 401


def test_expand_dry_run_returns_estimated_ideas(
    client: TestClient,
    enabled_dry_run_settings: Settings,
    authed_user: User,
) -> None:
    response = client.post(
        "/api/v1/keywords/expand",
        json={"seed": "money transfer", "locale": "en", "max_ideas": 5},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["seed"] == "money transfer"
    assert payload["provider"] == "mock"
    assert payload["estimated"] is True
    assert len(payload["ideas"]) == 5
    assert payload["ideas"][0]["phrase"] == "money transfer"
    assert payload["ideas"][0]["signals"]["volume_estimated"] is True


def test_overview_returns_seed_signals(
    client: TestClient,
    enabled_dry_run_settings: Settings,
    authed_user: User,
) -> None:
    response = client.post(
        "/api/v1/keywords/overview",
        json={"keyword": "money transfer", "locale": "en"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["keyword"] == "money transfer"
    assert payload["estimated"] is True
    assert payload["signals"]["volume_estimated"] is True
    assert payload["sample_ideas"]


def test_rank_check_dry_run(
    client: TestClient,
    enabled_dry_run_settings: Settings,
    authed_user: User,
) -> None:
    response = client.post(
        "/api/v1/keywords/rank-check",
        json={
            "domain": "yankidemo.co",
            "queries": ["best crm software", "crm comparison"],
            "locale": "en",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["domain"] == "yankidemo.co"
    assert payload["provider"] == "mock"
    assert len(payload["results"]) == 2
    assert all("measurable" in row for row in payload["results"])
