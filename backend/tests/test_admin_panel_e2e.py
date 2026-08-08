"""The Admin Platform, exercised as a client actually uses it.

Every other test of this milestone calls a service function directly. That
proves the functions work; it does not prove the *product* works, and the two
come apart in exactly the place that matters most here. `get_org_project()`
returning `None` for a stranger's project is not the same claim as "a real
signed-in HTTP request for another tenant's project gets a 404" — between them
sit the bearer token, `get_current_user`, `get_org_context`, the membership
lookup, and the route's own error handling. A bug in any of those is invisible
to a service-layer test.

So nothing here is overridden. Each test signs up over HTTP, logs in over HTTP,
carries the real access token it was issued, and receives whatever status code
the application actually produces. Two tenants exist for most of them, because
one tenant can never demonstrate isolation.

What this file is really checking:

* signup provisions a working tenant (org + workspace + owner membership) —
  a user who cannot make a request is not a user;
* one tenant's data is unreachable by another over HTTP, and indistinguishable
  from data that does not exist;
* the anonymous public surface is untouched by any of it;
* the audit trail records what the API did, with no credentials in it.
"""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import urlsplit

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import (
    AuditEvent,
    Membership,
    Organization,
    Project,
    SeoProject,
    Workspace,
)

SIGNUP_URL = "/api/v1/auth/signup"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
PROJECTS_URL = "/api/v1/seo-projects"
ANALYSES_URL = "/api/v1/analyses"

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def auth_settings(client: TestClient) -> Iterator[None]:
    """Real JWTs, so the token path is exercised rather than stubbed."""

    settings = Settings(
        jwt_secret_key=SecretStr("a" * 64),
        jwt_issuer="test-yanki-api",
        jwt_audience="test-yanki-web",
        auth_refresh_cookie_secure=False,
        # This suite is about TENANCY, not about the Site Audit kill-switch, so
        # it runs with the feature on. The distinction is not cosmetic: with the
        # flag off (its production default) no first crawl is queued, so
        # `latest_audit` is null and the cross-tenant audit-read test has no
        # audit to read — and, worse,
        # `test_queueing_an_audit_on_another_tenants_project_is_refused` would
        # still pass while asserting nothing about tenancy, because the 404 it
        # sees would be the flag refusing everyone rather than the org check
        # refusing Bob. A leakage test that passes for the wrong reason is worse
        # than one that fails. The kill-switch itself is covered in
        # tests/test_seo_projects_api.py, which is where it belongs.
        site_audit_enabled=True,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture(autouse=True)
def allow_test_domains(monkeypatch) -> None:
    """`.test` hosts resolve nowhere; the SSRF guard is fail-closed by design."""

    from app.api import seo_project_routes

    real_guard = seo_project_routes.is_public_url

    def guard(url: str) -> bool:
        host = urlsplit(url).hostname or ""
        return True if host.endswith(".test") else real_guard(url)

    monkeypatch.setattr(seo_project_routes, "is_public_url", guard)


class Tenant:
    """One signed-up account and the token it actually received."""

    def __init__(self, client: TestClient, email: str) -> None:
        signup = client.post(SIGNUP_URL, json={"email": email, "password": PASSWORD})
        assert signup.status_code == 201, signup.text
        login = client.post(LOGIN_URL, json={"email": email, "password": PASSWORD})
        assert login.status_code == 200, login.text
        self.email = email
        self.user_id = signup.json()["id"]
        self.token = login.json()["access_token"]

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


def _on_plan(db_session, tenant: Tenant, plan_key: str) -> None:
    """Put a freshly signed-up tenant on a tier.

    This suite is about **tenancy**, not about plan limits, and the two collide
    at exactly one point: Free allows one project and one site audit a month
    (P7.6), while isolation cannot be demonstrated with fewer than two of a
    thing. Left on Free, the two-project tests would fail on a 429 that has
    nothing to do with what they assert — and, worse, a cross-tenant test could
    pass because the second create was refused for the wrong reason. The plan
    limits themselves are proved in ``test_quota_enforcement.py``.
    """

    import uuid as _uuid

    from app.services import billing

    org = db_session.scalar(
        sa.select(Organization).where(
            Organization.owner_user_id == _uuid.UUID(tenant.user_id)
        )
    )
    assert org is not None, "signup must have provisioned an organization"
    billing.assign_plan(db_session, org.id, plan_key)
    db_session.commit()


@pytest.fixture()
def alice(client: TestClient, db_session) -> Tenant:
    tenant = Tenant(client, "alice@acme.test")
    _on_plan(db_session, tenant, "starter")
    return tenant


@pytest.fixture()
def bob(client: TestClient, db_session) -> Tenant:
    tenant = Tenant(client, "bob@globex.test")
    _on_plan(db_session, tenant, "starter")
    return tenant


def _create_project(client: TestClient, tenant: Tenant, domain: str) -> dict:
    response = client.post(
        PROJECTS_URL,
        json={
            "domain": domain,
            "page_limit": 5,
            "profile_id": "site_audit_mobile",
            "js_rendering": False,
        },
        headers=tenant.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------
# Signup produces a tenant that can actually make requests
# --------------------------------------------------------------------------


def test_signup_then_login_then_authenticated_request_all_work(client, db_session):
    """The whole chain, because a user who cannot make a request is not a user."""

    tenant = Tenant(client, "fresh@example.test")

    me = client.get(ME_URL, headers=tenant.headers)
    assert me.status_code == 200
    assert me.json()["email"] == "fresh@example.test"

    listing = client.get(PROJECTS_URL, headers=tenant.headers)
    assert listing.status_code == 200
    assert listing.json() == []


def test_signup_provisioned_a_complete_tenant(client, db_session):
    Tenant(client, "complete@example.test")

    org = db_session.scalar(sa.select(Organization).where(Organization.slug == "complete"))
    assert org is not None
    assert org.kind == "personal"

    workspace = db_session.scalar(sa.select(Workspace).where(Workspace.org_id == org.id))
    assert workspace is not None and workspace.is_default is True

    membership = db_session.scalar(sa.select(Membership).where(Membership.org_id == org.id))
    assert membership is not None and membership.role == "owner"


def test_an_unauthenticated_request_is_refused(client):
    assert client.get(PROJECTS_URL).status_code == 401


def test_a_garbage_token_is_refused(client):
    response = client.get(PROJECTS_URL, headers={"Authorization": "Bearer nonsense"})
    assert response.status_code == 401


# --------------------------------------------------------------------------
# Cross-tenant isolation, over HTTP — the claim that matters
# --------------------------------------------------------------------------


def test_a_project_is_invisible_to_the_other_tenant(client, alice, bob):
    project = _create_project(client, alice, "acme.test")

    mine = client.get(f"{PROJECTS_URL}/{project['id']}", headers=alice.headers)
    assert mine.status_code == 200

    theirs = client.get(f"{PROJECTS_URL}/{project['id']}", headers=bob.headers)
    assert theirs.status_code == 404


def test_a_cross_tenant_id_is_indistinguishable_from_a_missing_one(client, alice, bob):
    """Otherwise the response enumerates which project ids exist."""

    import uuid

    project = _create_project(client, alice, "acme.test")

    cross = client.get(f"{PROJECTS_URL}/{project['id']}", headers=bob.headers)
    absent = client.get(f"{PROJECTS_URL}/{uuid.uuid4()}", headers=bob.headers)

    assert cross.status_code == absent.status_code == 404
    assert cross.json() == absent.json()


def test_listing_only_ever_returns_your_own(client, alice, bob):
    _create_project(client, alice, "acme.test")
    _create_project(client, alice, "acme-two.test")
    _create_project(client, bob, "globex.test")

    alice_list = client.get(PROJECTS_URL, headers=alice.headers).json()
    bob_list = client.get(PROJECTS_URL, headers=bob.headers).json()

    assert {p["name"] for p in alice_list} == {"acme.test", "acme-two.test"}
    assert {p["name"] for p in bob_list} == {"globex.test"}


def test_queueing_an_audit_on_another_tenants_project_is_refused(client, alice, bob):
    project = _create_project(client, alice, "acme.test")

    response = client.post(
        f"{PROJECTS_URL}/{project['id']}/audits",
        json={"page_limit": 5, "profile_id": "site_audit_mobile", "js_rendering": False},
        headers=bob.headers,
    )
    assert response.status_code == 404


def test_reading_another_tenants_audit_is_refused(client, alice, bob, db_session):
    project = _create_project(client, alice, "acme.test")
    audit_id = project["latest_audit"]["id"]

    mine = client.get(f"{PROJECTS_URL}/{project['id']}/audits/{audit_id}", headers=alice.headers)
    assert mine.status_code == 200

    theirs = client.get(f"{PROJECTS_URL}/{project['id']}/audits/{audit_id}", headers=bob.headers)
    assert theirs.status_code == 404


def test_forging_an_org_header_you_do_not_belong_to_is_refused(client, alice, bob, db_session):
    """X-Org-Id requests a scope; it never grants one."""

    bobs_org = db_session.scalar(sa.select(Organization).where(Organization.slug == "bob"))
    assert bobs_org is not None

    response = client.get(
        PROJECTS_URL,
        headers={**alice.headers, "X-Org-Id": str(bobs_org.id)},
    )
    assert response.status_code == 403


def test_a_malformed_org_header_is_a_400_not_a_500(client, alice):
    response = client.get(PROJECTS_URL, headers={**alice.headers, "X-Org-Id": "not-a-uuid"})
    assert response.status_code == 400


# --------------------------------------------------------------------------
# The tenancy rows the API writes
# --------------------------------------------------------------------------


def test_creating_a_project_over_http_stamps_the_tenancy(client, alice, db_session):
    created = _create_project(client, alice, "acme.test")

    project = db_session.get(SeoProject, __import__("uuid").UUID(created["id"]))
    assert project is not None
    assert project.org_id is not None
    assert project.workspace_id is not None
    assert project.project_id is not None

    tracked = db_session.get(Project, project.project_id)
    assert tracked is not None
    assert tracked.org_id == project.org_id
    assert tracked.domain_key == "acme.test"


def test_two_tenants_may_track_the_same_domain(client, alice, bob, db_session):
    """Uniqueness is per-org. Two agencies auditing the same site is ordinary."""

    _create_project(client, alice, "shared.test")
    _create_project(client, bob, "shared.test")

    rows = db_session.scalars(sa.select(Project).where(Project.domain_key == "shared.test")).all()
    assert len(rows) == 2
    assert len({p.org_id for p in rows}) == 2


def test_the_same_tenant_cannot_track_one_domain_twice(client, alice):
    _create_project(client, alice, "acme.test")
    duplicate = client.post(
        PROJECTS_URL,
        json={
            "domain": "acme.test",
            "page_limit": 5,
            "profile_id": "site_audit_mobile",
            "js_rendering": False,
        },
        headers=alice.headers,
    )
    assert duplicate.status_code == 409


# --------------------------------------------------------------------------
# The audit trail records what the API actually did
# --------------------------------------------------------------------------


def test_the_api_writes_an_audit_trail(client, alice, db_session):
    _create_project(client, alice, "acme.test")

    actions = {row[0] for row in db_session.execute(sa.select(AuditEvent.action))}
    assert {"auth:signup", "auth:login", "project:create"} <= actions


def test_a_failed_login_over_http_is_audited_as_denied(client, db_session):
    Tenant(client, "who@example.test")
    response = client.post(LOGIN_URL, json={"email": "who@example.test", "password": "wrong"})
    assert response.status_code == 401

    denied = db_session.scalar(sa.select(AuditEvent).where(AuditEvent.outcome == "denied"))
    assert denied is not None
    assert denied.action == "auth:login"


def test_no_password_material_reaches_the_audit_trail_via_the_api(client, db_session):
    """The end-to-end version of the property the audit module exists for."""

    Tenant(client, "real@example.test")
    client.post(LOGIN_URL, json={"email": "real@example.test", "password": "wrong-one"})

    blob = " ".join(
        f"{e.before} {e.after} {e.detail} {e.actor_label}"
        for e in db_session.scalars(sa.select(AuditEvent))
    )
    assert PASSWORD not in blob
    assert "wrong-one" not in blob
    assert "argon2" not in blob


def test_audit_events_carry_the_acting_org(client, alice, db_session):
    _create_project(client, alice, "acme.test")

    event = db_session.scalar(sa.select(AuditEvent).where(AuditEvent.action == "project:create"))
    assert event is not None
    assert event.org_id is not None
    assert event.entity_type == "seo_project"


# --------------------------------------------------------------------------
# The anonymous surface is untouched — the P7.1 acceptance criterion
# --------------------------------------------------------------------------


def _legacy_public_analysis(db_session, url: str = "https://legacy.example.com"):
    """A row with no organization — every analysis in production before P7.6.

    Written directly rather than submitted, because there is no longer a route
    that produces one: submitting requires a credential and stamps the caller's
    org (ADR-45). These rows still exist and must still be readable by anyone
    holding the id, which is the promise this section is about.
    """

    from app.db.models import Analysis

    analysis = Analysis(url=url)
    db_session.add(analysis)
    db_session.commit()
    return analysis


def test_submitting_an_analysis_without_a_credential_is_refused(client, db_session):
    """The one behavioural change P7.6 makes to the public surface (ADR-45).

    It was open, and unused-while-open: every page that submits one has been
    behind sign-in since session 21. An endpoint that spends money at a paid
    vendor with no tenant attached cannot be metered, so closing it is what
    makes a plan tier mean anything.
    """

    from app.db.models import Analysis

    submit = client.post(ANALYSES_URL, json={"url": "https://example.com"})
    assert submit.status_code == 401
    assert db_session.scalar(sa.select(sa.func.count()).select_from(Analysis)) == 0


def test_an_organization_less_analysis_is_still_world_readable(client, db_session):
    """The capability URL survives. Every pre-P7.6 row and every checker run
    has no organization, and `tenancy.readable_analysis` keeps serving them to
    anyone holding the id — including with no bearer token at all."""

    analysis = _legacy_public_analysis(db_session)

    read = client.get(f"{ANALYSES_URL}/{analysis.id}")
    assert read.status_code == 200
    assert read.json()["url"] == "https://legacy.example.com"


def test_a_signed_in_user_can_still_read_an_organization_less_analysis(
    client, alice, db_session
):
    analysis = _legacy_public_analysis(db_session)

    read = client.get(f"{ANALYSES_URL}/{analysis.id}", headers=alice.headers)
    assert read.status_code == 200


def test_one_tenants_analysis_is_unreachable_by_the_other_and_by_the_public(
    client, alice, bob, db_session
):
    """The leakage test the new attribution makes necessary.

    Stamping `org_id` on a run is not free: the moment an analysis belongs to
    somebody, serving it to everybody is a cross-tenant read. So the same 404
    that hides another tenant's project must hide their analysis — and it must
    look identical to a nonexistent id, or the response enumerates which runs
    exist.
    """

    # A genuinely public host: the `.test` escape hatch above patches the SSRF
    # guard the *project* routes import, not this one.
    submit = client.post(
        ANALYSES_URL, json={"url": "https://example.com"}, headers=alice.headers
    )
    assert submit.status_code == 202, submit.text
    analysis_id = submit.json()["id"]

    assert client.get(f"{ANALYSES_URL}/{analysis_id}", headers=alice.headers).status_code == 200
    assert client.get(f"{ANALYSES_URL}/{analysis_id}", headers=bob.headers).status_code == 404
    assert client.get(f"{ANALYSES_URL}/{analysis_id}").status_code == 404

    import uuid as _uuid

    missing = client.get(f"{ANALYSES_URL}/{_uuid.uuid4()}", headers=bob.headers)
    theirs = client.get(f"{ANALYSES_URL}/{analysis_id}", headers=bob.headers)
    assert missing.status_code == theirs.status_code == 404
    assert missing.json() == theirs.json()


def test_the_analysis_response_did_not_grow_an_org_field(client, db_session):
    """Contract drift guard — attribution is a column, not a payload field."""

    analysis = _legacy_public_analysis(db_session)
    body = client.get(f"{ANALYSES_URL}/{analysis.id}").json()
    assert "org_id" not in body
    assert "organization" not in body


def test_the_waitlist_still_takes_anonymous_signups(client):
    response = client.post("/api/v1/waitlist", json={"email": "someone@example.test"})
    assert response.status_code == 202


# --------------------------------------------------------------------------
# RBAC and quota, exercised through the dependency the routes would use
# --------------------------------------------------------------------------


def test_a_demoted_member_loses_access_on_the_very_next_request(client, alice, db_session):
    """Roles are read per request, not baked into the token.

    This is the property that makes a role change take effect. If the role were
    carried in the JWT, revoking someone would do nothing until their token
    expired — which for a 15-minute access token is 15 minutes of a fired
    contractor still being an owner.
    """

    from app.db.models import User
    from app.services.permissions import ORG_DELETE, can
    from app.services.tenancy import resolve_org_context

    user = db_session.scalar(sa.select(User).where(User.email == alice.email))
    context = resolve_org_context(db_session, user=user)
    assert context.role == "owner"
    assert can(context, ORG_DELETE) is True

    membership = db_session.scalar(sa.select(Membership).where(Membership.user_id == user.id))
    membership.role = "viewer"
    db_session.commit()

    # Same user, same token, next request — the role is re-read.
    context = resolve_org_context(db_session, user=user)
    assert context.role == "viewer"
    assert can(context, ORG_DELETE) is False


def test_a_deactivated_member_is_locked_out_and_stays_locked_out(client, alice, db_session):
    """Deactivation denies access, and the self-heal path must not undo it.

    `resolve_org_context` get-or-creates a home for a user who has none, which
    is what rescues a half-failed signup. The risk is that the same code
    silently REVIVES somebody who was deliberately removed — healing a missing
    membership and reviving a revoked one look almost identical. They are
    opposites, so this asserts the distinction directly.
    """

    from app.db.models import User
    from app.services.tenancy import OrgScopeRequired, resolve_org_context

    user = db_session.scalar(sa.select(User).where(User.email == alice.email))
    membership = db_session.scalar(sa.select(Membership).where(Membership.user_id == user.id))
    membership.status = "deactivated"
    db_session.commit()

    with pytest.raises(OrgScopeRequired):
        resolve_org_context(db_session, user=user)

    db_session.rollback()
    membership = db_session.scalar(sa.select(Membership).where(Membership.user_id == user.id))
    assert membership.status == "deactivated", "the resolver must not revive them"


def test_a_deactivated_member_gets_403_over_http(client, alice, db_session):
    """The security property, seen the way an attacker would."""

    from app.db.models import User

    user = db_session.scalar(sa.select(User).where(User.email == alice.email))
    membership = db_session.scalar(sa.select(Membership).where(Membership.user_id == user.id))
    membership.status = "deactivated"
    db_session.commit()

    # Same valid token — access is revoked by state, not by token expiry.
    response = client.get(PROJECTS_URL, headers=alice.headers)
    assert response.status_code == 403


def test_an_owner_whose_membership_row_vanished_is_let_back_in(client, alice, db_session):
    """The opposite case: a missing row is repaired, not treated as revocation."""

    from app.db.models import User
    from app.services.tenancy import resolve_org_context

    user = db_session.scalar(sa.select(User).where(User.email == alice.email))
    original = db_session.scalar(sa.select(Membership).where(Membership.user_id == user.id))
    original_org = original.org_id
    db_session.delete(original)
    db_session.commit()

    context = resolve_org_context(db_session, user=user)
    assert context.org_id == original_org, "back into their own org, not a new one"
    assert context.role == "owner"


def test_the_permission_dependency_refuses_and_audits(client, alice, db_session):
    from app.api.org_dependencies import requires
    from app.services.permissions import BILLING_MANAGE

    dependency = requires(BILLING_MANAGE)
    app.dependency_overrides.clear()

    # Build the context the way a request would, then demote.
    from app.db.models import User
    from app.services.tenancy import resolve_org_context

    user = db_session.scalar(sa.select(User).where(User.email == alice.email))
    membership = db_session.scalar(sa.select(Membership).where(Membership.user_id == user.id))
    membership.role = "viewer"
    db_session.commit()

    context = resolve_org_context(db_session, user=user)
    with pytest.raises(Exception) as excinfo:
        dependency(context, db_session)
    assert getattr(excinfo.value, "status_code", None) == 403

    denied = db_session.scalar(
        sa.select(AuditEvent).where(
            AuditEvent.action == BILLING_MANAGE, AuditEvent.outcome == "denied"
        )
    )
    assert denied is not None, "a refusal is an event worth having"


def test_quota_is_enforced_for_a_real_signed_up_org(client, db_session):
    """The free tier's allowance, applied to an org that came from signup.

    A tenant of its own rather than ``alice``, who is put on Starter so the
    isolation tests can hold two projects. This one is specifically about the
    state **every production organization is in**: signed up, never given a
    subscription, falling back to Free.
    """

    from app.db.models import User
    from app.services import billing
    from app.services.tenancy import resolve_org_context

    tenant = Tenant(client, "unsubscribed@example.test")

    user = db_session.scalar(sa.select(User).where(User.email == tenant.email))
    context = resolve_org_context(db_session, user=user)
    assert billing.plan_for_org(db_session, context.org_id) is None

    # No subscription → Free → 5 analyses.
    assert billing.limit_for(db_session, context.org_id, billing.METRIC_ANALYSES) == 5
    for _ in range(5):
        billing.consume_quota(db_session, context.org_id, billing.METRIC_ANALYSES)
    db_session.commit()

    with pytest.raises(billing.QuotaExceeded):
        billing.consume_quota(db_session, context.org_id, billing.METRIC_ANALYSES)
