"""Shared test fixtures.

Everything here runs against a fresh in-memory SQLite database — no external
services, instant and hermetic. A ``StaticPool`` keeps a single connection so the
API client (via a dependency-overridden session) and the raw ``db_session`` see
the same in-memory data.

**The plan catalog is seeded, because production's is** (migration
``0016_seed_plans``). Before P7.6 that made no difference, since nothing read a
plan. Now that quotas are enforced, a suite running against an empty catalog
would be testing a deployment that cannot exist — and would quietly prove that
every route works when no limit applies. So the default test organization is on
**Free**, with Free's real limits: 5 analyses a month, 1 site audit, 1 project.

A test that needs more headroom asks for it explicitly with the ``on_plan``
fixture. That is deliberately noisier than a global "unlimited" default: a test
that has to say ``on_plan(org, "pro")`` is a test whose author saw the limit.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.config import Settings
from app.db.base import Base
from app.db.models import Analysis
from app.db.session import get_session
from app.services import billing


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng)
    with Session(eng) as seed_session:
        billing.seed_plans(seed_session)
        seed_session.commit()
    try:
        yield eng
    finally:
        Base.metadata.drop_all(eng)
        eng.dispose()


@pytest.fixture()
def on_plan(db_session):
    """Put an organization on a named tier for the rest of the test.

    ``on_plan(org_id, "enterprise")`` is the escape hatch for suites that are
    about something other than quotas and need more than Free allows.
    """

    def _assign(org_id: uuid.UUID, plan_key: str = "enterprise"):
        subscription = billing.assign_plan(db_session, org_id, plan_key)
        db_session.commit()
        return subscription

    return _assign


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


@pytest.fixture()
def db_session(session_factory):
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def settings():
    return Settings()


@pytest.fixture(autouse=True)
def resolve_test_domains(monkeypatch):
    """Let ``*.test`` hosts through SSRF guard without live DNS (hermetic CI)."""

    from urllib.parse import urlsplit

    from app.api import routes, seo_project_routes

    real_routes = routes.is_public_url
    real_seo = seo_project_routes.is_public_url

    def guard(url: str) -> bool:
        host = urlsplit(url).hostname or ""
        if host.endswith(".test"):
            return True
        return real_routes(url)

    def seo_guard(url: str) -> bool:
        host = urlsplit(url).hostname or ""
        if host.endswith(".test"):
            return True
        return real_seo(url)

    monkeypatch.setattr(routes, "is_public_url", guard)
    monkeypatch.setattr(seo_project_routes, "is_public_url", seo_guard)


@pytest.fixture()
def client(session_factory):
    def override_get_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def signed_in(db_session):
    """A signed-in owner of a fresh personal organization.

    Submitting an analysis needs a credential and an organization from P7.6 on
    (ADR-45), so the suites that exercise that route need somebody to be. The
    dependency override is the same one the SEO-project tests use — it swaps the
    bearer-token dependency rather than minting a JWT, because these tests are
    about the route's behaviour and not about token parsing, which
    ``test_tokens`` and ``test_auth_api`` cover on their own.

    ``plan_key`` puts the org on a tier. Left ``None`` the org has no
    subscription and falls back to Free, exactly as every production
    organization does today.
    """

    from app.api.auth_dependencies import get_current_user, get_optional_user
    from app.db.models import User
    from app.services.auth import hash_password
    from app.services.tenancy import provision_personal_org

    def _sign_in(email: str = "member@example.test", plan_key: str | None = None):
        user = User(email=email, password_hash=hash_password("correct-horse"))
        db_session.add(user)
        db_session.flush()
        org = provision_personal_org(db_session, user)
        if plan_key is not None:
            billing.assign_plan(db_session, org.id, plan_key)
        db_session.commit()
        # Both, and this is not belt-and-braces. Routes open to either audience
        # resolve the caller through `get_optional_user` (GET /analyses/{id} is
        # the one that matters here), so overriding only the strict dependency
        # would sign the caller in for writes and leave them anonymous for
        # reads — which is precisely the combination that makes an org-scoped
        # read 404 for the person who just created the row.
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_optional_user] = lambda: user
        return user, org

    yield _sign_in
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_optional_user, None)


@pytest.fixture()
def make_analysis(db_session):
    """Factory that inserts an Analysis row and returns it."""

    def _make(url: str = "https://example.com", **kwargs) -> Analysis:
        analysis = Analysis(url=url, **kwargs)
        db_session.add(analysis)
        db_session.commit()
        return analysis

    return _make
