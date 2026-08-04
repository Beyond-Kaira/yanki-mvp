"""Authenticated SEO project and Site Audit persistence/API tests."""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth_dependencies import get_current_user
from app.api.main import app
from app.db.models import SeoProject, SiteAudit, SiteAuditPage, User
from app.services.auth import hash_password

PROJECTS_URL = "/api/v1/seo-projects"


@pytest.fixture(autouse=True)
def resolve_reserved_test_domains(monkeypatch) -> None:
    """Keep API tests deterministic while production DNS remains fail closed."""

    from app.api import seo_project_routes

    real_guard = seo_project_routes.is_public_url

    def test_guard(url: str) -> bool:
        host = urlsplit(url).hostname or ""
        return True if host.endswith(".test") else real_guard(url)

    monkeypatch.setattr(seo_project_routes, "is_public_url", test_guard)


@pytest.fixture()
def make_user(db_session: Session) -> Callable[[str], User]:
    def _make(email: str) -> User:
        user = User(email=email, password_hash=hash_password("correct-horse"))
        db_session.add(user)
        db_session.commit()
        return user

    return _make


def _authenticate_as(user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


def _create_project(
    client: TestClient,
    *,
    domain: str = "example.test",
    name: str | None = None,
    page_limit: int = 10,
) -> dict:
    payload: dict[str, object] = {
        "domain": domain,
        "page_limit": page_limit,
        "profile_id": "site_audit_mobile",
        "js_rendering": True,
    }
    if name is not None:
        payload["name"] = name

    response = client.post(PROJECTS_URL, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_projects_require_authentication(client: TestClient) -> None:
    list_response = client.get(PROJECTS_URL)
    create_response = client.post(PROJECTS_URL, json={"domain": "example.test"})

    assert list_response.status_code == 401
    assert create_response.status_code == 401
    assert list_response.headers["www-authenticate"] == "Bearer"


def test_create_project_normalizes_domain_and_queues_first_audit(
    client: TestClient,
    db_session: Session,
    make_user: Callable[[str], User],
) -> None:
    user = make_user("owner@example.com")
    _authenticate_as(user)

    body = _create_project(
        client,
        domain=" HTTPS://WWW.Example.Test/some/page?campaign=1#hero ",
        page_limit=25,
    )

    assert body["name"] == "example.test"
    assert body["domain"] == "https://www.example.test/"
    assert body["latest_audit"]["status"] == "queued"
    assert body["latest_audit"]["page_limit"] == 25
    assert body["latest_audit"]["profile_id"] == "site_audit_mobile"
    assert body["latest_audit"]["js_rendering"] is True

    project = db_session.scalar(select(SeoProject))
    audit = db_session.scalar(select(SiteAudit))

    assert project is not None
    assert audit is not None
    assert project.user_id == user.id
    assert project.domain_key == "example.test"
    assert audit.project_id == project.id
    assert audit.status == "queued"


def test_duplicate_domain_is_rejected_per_user_but_allowed_for_another_user(
    client: TestClient,
    db_session: Session,
    make_user: Callable[[str], User],
) -> None:
    first_user = make_user("first@example.com")
    second_user = make_user("second@example.com")

    _authenticate_as(first_user)
    _create_project(client, domain="https://www.example.test/")

    duplicate = client.post(PROJECTS_URL, json={"domain": "example.test/about"})
    assert duplicate.status_code == 409

    _authenticate_as(second_user)
    second_project = _create_project(client, domain="http://example.test")
    assert second_project["domain"] == "http://example.test/"

    project_count = db_session.scalar(select(func.count()).select_from(SeoProject))
    assert project_count == 2


def test_project_list_and_detail_never_cross_user_boundary(
    client: TestClient,
    make_user: Callable[[str], User],
) -> None:
    owner = make_user("owner@example.com")
    stranger = make_user("stranger@example.com")

    _authenticate_as(owner)
    owned_project = _create_project(client, domain="owned.test", name="Owned site")

    _authenticate_as(stranger)
    _create_project(client, domain="stranger.test", name="Stranger site")

    list_response = client.get(PROJECTS_URL)
    hidden_detail = client.get(f"{PROJECTS_URL}/{owned_project['id']}")
    hidden_audit = client.get(
        f"{PROJECTS_URL}/{owned_project['id']}/audits/"
        f"{owned_project['latest_audit']['id']}"
    )

    assert list_response.status_code == 200
    assert [project["name"] for project in list_response.json()] == ["Stranger site"]
    assert hidden_detail.status_code == 404
    assert hidden_audit.status_code == 404


def test_completed_project_can_queue_rerun_but_two_active_audits_are_rejected(
    client: TestClient,
    db_session: Session,
    make_user: Callable[[str], User],
) -> None:
    user = make_user("owner@example.com")
    _authenticate_as(user)
    project = _create_project(client)

    first_audit = db_session.scalar(select(SiteAudit))
    assert first_audit is not None
    first_audit.status = "done"
    first_audit.progress = 100
    db_session.commit()

    rerun_response = client.post(
        f"{PROJECTS_URL}/{project['id']}/audits",
        json={
            "page_limit": 50,
            "profile_id": "site_audit_desktop",
            "js_rendering": False,
        },
    )
    conflict_response = client.post(
        f"{PROJECTS_URL}/{project['id']}/audits",
        json={},
    )

    assert rerun_response.status_code == 202
    assert rerun_response.json()["status"] == "queued"
    assert rerun_response.json()["page_limit"] == 50
    assert rerun_response.json()["profile_id"] == "site_audit_desktop"
    assert rerun_response.json()["js_rendering"] is False
    assert conflict_response.status_code == 409


def test_audit_detail_returns_structured_page_findings(
    client: TestClient,
    db_session: Session,
    make_user: Callable[[str], User],
) -> None:
    user = make_user("owner@example.com")
    _authenticate_as(user)
    project_body = _create_project(client)

    audit = db_session.scalar(select(SiteAudit))
    assert audit is not None
    audit.status = "done"
    audit.progress = 100
    audit.pages_discovered = 1
    audit.pages_crawled = 1
    audit.total_errors = 1
    audit.health_score = 85
    page = SiteAuditPage(
        audit_id=audit.id,
        requested_url="https://example.test/",
        final_url="https://example.test/",
        status_code=200,
        title="Example",
        h1_count=0,
        meta_description="Example description",
        html_lang="en",
        issues=[
            {
                "code": "missing_h1",
                "severity": "error",
                "message": "Page does not have an H1 heading.",
                "details": {},
            }
        ],
        schemas=[
            {
                "type": "Organization",
                "syntax_valid": True,
                "structure_status": "valid",
                "details": {
                    "valid_fields": ["name"],
                    "invalid_fields": [],
                },
                "error_detail": None,
            }
        ],
    )
    db_session.add(page)
    db_session.commit()

    response = client.get(
        f"{PROJECTS_URL}/{project_body['id']}/audits/{audit.id}"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["health_score"] == 85
    assert body["pages"][0]["issues"][0]["code"] == "missing_h1"
    assert body["pages"][0]["schemas"][0]["type"] == "Organization"


def test_private_network_domain_is_rejected_without_persisting(
    client: TestClient,
    db_session: Session,
    make_user: Callable[[str], User],
) -> None:
    _authenticate_as(make_user("owner@example.com"))

    response = client.post(PROJECTS_URL, json={"domain": "http://127.0.0.1:8000"})

    assert response.status_code == 422
    assert db_session.scalar(select(func.count()).select_from(SeoProject)) == 0
    assert db_session.scalar(select(func.count()).select_from(SiteAudit)) == 0
