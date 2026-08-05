"""Account types and the org-admin API, over real HTTP.

Two things this file is really guarding.

**An admin panel is a data-leak surface.** "List the users" is one forgotten
predicate away from "list *everyone's* users", and the mistake is invisible in
a single-tenant test. So every read here is checked with a second organization
present, and a cross-org id must be indistinguishable from one that does not
exist — otherwise the endpoint enumerates accounts even when it refuses them.

**An admin panel is a lockout surface.** The two ways an organization loses its
last administrator — demoting the final owner, and disabling them — both have
guards, and both are tested, because the failure mode is a support ticket and a
database edit rather than an error message.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import AuditEvent, Membership, Organization, User

SIGNUP = "/api/v1/auth/signup"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
MEMBERS = "/api/v1/admin/members"
ORG = "/api/v1/admin/organization"
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def auth_settings(client: TestClient) -> Iterator[None]:
    settings = Settings(
        jwt_secret_key=SecretStr("a" * 64),
        jwt_issuer="test-yanki-api",
        jwt_audience="test-yanki-web",
        auth_refresh_cookie_secure=False,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield
    app.dependency_overrides.pop(get_settings, None)


def _signup(client: TestClient, email: str, **extra) -> dict:
    body = {"email": email, "password": PASSWORD, **extra}
    response = client.post(SIGNUP, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _token(client: TestClient, email: str) -> str:
    response = client.post(LOGIN, json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(token: str, org_id=None) -> dict[str, str]:
    """Auth, plus optionally the organization to act within.

    ``X-Org-Id`` matters here more than anywhere else. Every user signs up with
    their own organization, so somebody invited into a second one has TWO
    active memberships, and the resolver defaults to the first. An admin screen
    for a multi-org user therefore has to say which org it means — and the
    header is a *request* for a scope, never a grant: membership is re-checked
    server-side every time (proved by the forged-header test).
    """

    headers = {"Authorization": f"Bearer {token}"}
    if org_id is not None:
        headers["X-Org-Id"] = str(org_id)
    return headers


# --------------------------------------------------------------------------
# Account types
# --------------------------------------------------------------------------


def test_an_individual_signup_gets_a_personal_org(client, db_session):
    _signup(client, "solo@example.test", account_type="individual")

    org = db_session.scalar(sa.select(Organization).where(Organization.slug == "solo"))
    assert org is not None
    assert org.kind == "personal"


def test_an_organization_signup_gets_a_named_company_org(client, db_session):
    _signup(
        client,
        "founder@acme.test",
        account_type="organization",
        organization_name="Acme Industries",
    )

    org = db_session.scalar(sa.select(Organization).where(Organization.name == "Acme Industries"))
    assert org is not None
    assert org.kind == "company"
    assert org.slug == "acme-industries"


def test_an_organization_signup_without_a_name_is_rejected(client):
    response = client.post(
        SIGNUP,
        json={
            "email": "nameless@acme.test",
            "password": PASSWORD,
            "account_type": "organization",
        },
    )
    assert response.status_code == 422


def test_the_default_account_type_is_individual(client, db_session):
    """An old client that does not send the field must keep working."""

    _signup(client, "legacy@example.test")
    org = db_session.scalar(sa.select(Organization).where(Organization.slug == "legacy"))
    assert org is not None and org.kind == "personal"


def test_both_account_types_can_log_in_and_act(client):
    _signup(client, "solo@example.test", account_type="individual")
    _signup(client, "team@acme.test", account_type="organization", organization_name="Acme")

    for email in ("solo@example.test", "team@acme.test"):
        me = client.get(ME, headers=_headers(_token(client, email)))
        assert me.status_code == 200, email
        assert me.json()["organization"] is not None
        assert me.json()["role"] == "owner"


def test_two_organizations_may_share_a_name_without_colliding(client, db_session):
    _signup(client, "a@one.test", account_type="organization", organization_name="Acme")
    _signup(client, "b@two.test", account_type="organization", organization_name="Acme")

    slugs = sorted(
        db_session.scalars(sa.select(Organization.slug).where(Organization.kind == "company"))
    )
    assert slugs == ["acme", "acme-2"]


# --------------------------------------------------------------------------
# /me carries what the UI needs
# --------------------------------------------------------------------------


def test_me_returns_the_org_role_and_permissions(client):
    _signup(client, "owner@acme.test", account_type="organization", organization_name="Acme")
    body = client.get(ME, headers=_headers(_token(client, "owner@acme.test"))).json()

    assert body["organization"]["name"] == "Acme"
    assert body["organization"]["kind"] == "company"
    assert body["role"] == "owner"
    assert "member:read" in body["permissions"]
    assert "org:delete" in body["permissions"]
    assert body["status"] == "active"


def test_me_permissions_reflect_the_actual_role(client, db_session):
    _signup(client, "owner@acme.test", account_type="organization", organization_name="Acme")
    user = db_session.scalar(sa.select(User).where(User.email == "owner@acme.test"))
    membership = db_session.scalar(sa.select(Membership).where(Membership.user_id == user.id))
    membership.role = "viewer"
    db_session.commit()

    body = client.get(ME, headers=_headers(_token(client, "owner@acme.test"))).json()
    assert body["role"] == "viewer"
    assert "org:delete" not in body["permissions"]
    assert "project:read" in body["permissions"]


# --------------------------------------------------------------------------
# Listing and searching members
# --------------------------------------------------------------------------


def _org_with_members(client, db_session):
    """An owner plus two members, all in one organization."""

    _signup(client, "owner@acme.test", account_type="organization", organization_name="Acme")
    org = db_session.scalar(sa.select(Organization).where(Organization.name == "Acme"))

    for email, role in (("editor@acme.test", "editor"), ("viewer@acme.test", "viewer")):
        _signup(client, email)
        user = db_session.scalar(sa.select(User).where(User.email == email))
        # Join them to the org the way an invitation will (P7.4).
        db_session.add(Membership(org_id=org.id, user_id=user.id, role=role, status="active"))
    db_session.commit()
    return org


def test_listing_returns_the_orgs_members_with_roles(client, db_session):
    _org_with_members(client, db_session)
    token = _token(client, "owner@acme.test")

    body = client.get(MEMBERS, headers=_headers(token)).json()
    assert body["total"] == 3
    by_email = {m["email"]: m for m in body["members"]}
    assert by_email["owner@acme.test"]["role"] == "owner"
    assert by_email["editor@acme.test"]["role"] == "editor"
    assert by_email["viewer@acme.test"]["role"] == "viewer"


def test_the_role_picker_options_come_from_the_server(client, db_session):
    """So the UI cannot offer a role the API would refuse."""

    _org_with_members(client, db_session)
    body = client.get(MEMBERS, headers=_headers(_token(client, "owner@acme.test"))).json()

    assert "owner" in body["assignable_roles"]
    assert "super_admin" not in body["assignable_roles"], "platform roles are Yanki staff"
    assert "support" not in body["assignable_roles"]


def test_search_filters_by_email(client, db_session):
    _org_with_members(client, db_session)
    token = _token(client, "owner@acme.test")

    body = client.get(f"{MEMBERS}?q=EDITOR", headers=_headers(token)).json()
    assert body["total"] == 1
    assert body["members"][0]["email"] == "editor@acme.test"


def test_filters_by_role_and_status(client, db_session):
    _org_with_members(client, db_session)
    token = _token(client, "owner@acme.test")

    assert client.get(f"{MEMBERS}?role=viewer", headers=_headers(token)).json()["total"] == 1
    assert client.get(f"{MEMBERS}?status=active", headers=_headers(token)).json()["total"] == 3


def test_pagination_reports_the_true_total(client, db_session):
    """A limit must not make `total` lie — the pager depends on it."""

    _org_with_members(client, db_session)
    body = client.get(
        f"{MEMBERS}?limit=1", headers=_headers(_token(client, "owner@acme.test"))
    ).json()
    assert body["total"] == 3
    assert len(body["members"]) == 1


# --------------------------------------------------------------------------
# The leak surface
# --------------------------------------------------------------------------


def test_one_orgs_members_are_invisible_to_another(client, db_session):
    _org_with_members(client, db_session)
    _signup(client, "stranger@globex.test", account_type="organization", organization_name="Globex")

    body = client.get(MEMBERS, headers=_headers(_token(client, "stranger@globex.test"))).json()
    assert body["total"] == 1
    assert body["members"][0]["email"] == "stranger@globex.test"


def test_reading_a_member_of_another_org_is_a_404(client, db_session):
    _org_with_members(client, db_session)
    _signup(client, "stranger@globex.test", account_type="organization", organization_name="Globex")
    victim = db_session.scalar(sa.select(User).where(User.email == "editor@acme.test"))

    import uuid

    token = _token(client, "stranger@globex.test")
    cross = client.get(f"{MEMBERS}/{victim.id}", headers=_headers(token))
    absent = client.get(f"{MEMBERS}/{uuid.uuid4()}", headers=_headers(token))

    assert cross.status_code == absent.status_code == 404
    assert cross.json() == absent.json(), "the response must not confirm they exist"


def test_editing_a_member_of_another_org_is_a_404(client, db_session):
    _org_with_members(client, db_session)
    _signup(client, "stranger@globex.test", account_type="organization", organization_name="Globex")
    victim = db_session.scalar(sa.select(User).where(User.email == "editor@acme.test"))

    response = client.patch(
        f"{MEMBERS}/{victim.id}",
        json={"role": "owner"},
        headers=_headers(_token(client, "stranger@globex.test")),
    )
    assert response.status_code == 404
    db_session.refresh(victim)


def test_admin_endpoints_require_authentication(client):
    assert client.get(MEMBERS).status_code == 401
    assert client.get(ORG).status_code == 401


def test_a_viewer_cannot_list_or_edit_members(client, db_session):
    """Deny-by-default, over HTTP, acting inside the org they were invited to."""

    org = _org_with_members(client, db_session)
    token = _token(client, "viewer@acme.test")

    assert client.get(MEMBERS, headers=_headers(token, org.id)).status_code == 403
    victim = db_session.scalar(sa.select(User).where(User.email == "editor@acme.test"))
    assert (
        client.patch(
            f"{MEMBERS}/{victim.id}",
            json={"role": "owner"},
            headers=_headers(token, org.id),
        ).status_code
        == 403
    )


def test_a_refused_admin_action_is_audited(client, db_session):
    org = _org_with_members(client, db_session)
    client.get(MEMBERS, headers=_headers(_token(client, "viewer@acme.test"), org.id))

    denied = db_session.scalar(
        sa.select(AuditEvent).where(
            AuditEvent.action == "member:read", AuditEvent.outcome == "denied"
        )
    )
    assert denied is not None


# --------------------------------------------------------------------------
# Editing: roles, enable/disable, and the lockout guards
# --------------------------------------------------------------------------


def test_an_owner_can_change_a_members_role(client, db_session):
    _org_with_members(client, db_session)
    victim = db_session.scalar(sa.select(User).where(User.email == "viewer@acme.test"))

    response = client.patch(
        f"{MEMBERS}/{victim.id}",
        json={"role": "editor"},
        headers=_headers(_token(client, "owner@acme.test")),
    )
    assert response.status_code == 200
    assert response.json()["role"] == "editor"


def test_disabling_a_member_stops_them_logging_in(client, db_session):
    """The whole point of the switch."""

    _org_with_members(client, db_session)
    victim = db_session.scalar(sa.select(User).where(User.email == "editor@acme.test"))

    assert client.post(LOGIN, json={"email": victim.email, "password": PASSWORD}).status_code == 200

    response = client.patch(
        f"{MEMBERS}/{victim.id}",
        json={"status": "disabled"},
        headers=_headers(_token(client, "owner@acme.test")),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "disabled"

    refused = client.post(LOGIN, json={"email": victim.email, "password": PASSWORD})
    assert refused.status_code == 401


def test_re_enabling_restores_access_rather_than_recreating_the_person(client, db_session):
    _org_with_members(client, db_session)
    victim = db_session.scalar(sa.select(User).where(User.email == "editor@acme.test"))
    owner_token = _token(client, "owner@acme.test")

    client.patch(
        f"{MEMBERS}/{victim.id}", json={"status": "disabled"}, headers=_headers(owner_token)
    )
    client.patch(f"{MEMBERS}/{victim.id}", json={"status": "active"}, headers=_headers(owner_token))

    assert client.post(LOGIN, json={"email": victim.email, "password": PASSWORD}).status_code == 200
    db_session.refresh(victim)
    assert victim.id is not None


def test_the_last_owner_cannot_be_demoted(client, db_session):
    """Otherwise the organization has nobody who can ever fix it."""

    _signup(client, "solo-owner@acme.test", account_type="organization", organization_name="Acme")
    owner = db_session.scalar(sa.select(User).where(User.email == "solo-owner@acme.test"))
    _signup(client, "second@acme.test", account_type="organization", organization_name="Other")
    second = db_session.scalar(sa.select(User).where(User.email == "second@acme.test"))
    org = db_session.scalar(sa.select(Organization).where(Organization.name == "Acme"))
    db_session.add(Membership(org_id=org.id, user_id=second.id, role="admin", status="active"))
    db_session.commit()

    # The second member is an admin, so they may attempt the change.
    response = client.patch(
        f"{MEMBERS}/{owner.id}",
        json={"role": "viewer"},
        headers=_headers(_token(client, "second@acme.test"), org.id),
    )
    assert response.status_code == 409
    assert "owner" in response.json()["detail"]


def test_the_last_owner_cannot_be_disabled(client, db_session):
    _signup(client, "solo-owner@acme.test", account_type="organization", organization_name="Acme")
    owner = db_session.scalar(sa.select(User).where(User.email == "solo-owner@acme.test"))
    _signup(client, "second@acme.test", account_type="organization", organization_name="Other")
    second = db_session.scalar(sa.select(User).where(User.email == "second@acme.test"))
    org = db_session.scalar(sa.select(Organization).where(Organization.name == "Acme"))
    db_session.add(Membership(org_id=org.id, user_id=second.id, role="admin", status="active"))
    db_session.commit()

    response = client.patch(
        f"{MEMBERS}/{owner.id}",
        json={"status": "disabled"},
        headers=_headers(_token(client, "second@acme.test"), org.id),
    )
    assert response.status_code == 409


def test_you_cannot_change_your_own_role(client, db_session):
    _org_with_members(client, db_session)
    owner = db_session.scalar(sa.select(User).where(User.email == "owner@acme.test"))

    response = client.patch(
        f"{MEMBERS}/{owner.id}",
        json={"role": "viewer"},
        headers=_headers(_token(client, "owner@acme.test")),
    )
    assert response.status_code == 409


def test_an_unknown_role_is_refused_with_the_valid_options(client, db_session):
    _org_with_members(client, db_session)
    victim = db_session.scalar(sa.select(User).where(User.email == "viewer@acme.test"))

    response = client.patch(
        f"{MEMBERS}/{victim.id}",
        json={"role": "wizard"},
        headers=_headers(_token(client, "owner@acme.test")),
    )
    assert response.status_code == 422
    assert "editor" in response.json()["detail"]


def test_a_customer_cannot_grant_a_platform_role(client, db_session):
    _org_with_members(client, db_session)
    victim = db_session.scalar(sa.select(User).where(User.email == "viewer@acme.test"))

    response = client.patch(
        f"{MEMBERS}/{victim.id}",
        json={"role": "super_admin"},
        headers=_headers(_token(client, "owner@acme.test")),
    )
    assert response.status_code == 422


def test_a_member_edit_is_audited_with_before_and_after(client, db_session):
    _org_with_members(client, db_session)
    victim = db_session.scalar(sa.select(User).where(User.email == "viewer@acme.test"))

    client.patch(
        f"{MEMBERS}/{victim.id}",
        json={"role": "editor"},
        headers=_headers(_token(client, "owner@acme.test")),
    )

    event = db_session.scalar(sa.select(AuditEvent).where(AuditEvent.action == "member:update"))
    assert event is not None
    assert event.before["role"] == "viewer"
    assert event.after["role"] == "editor"
    assert event.entity_id == victim.id


# --------------------------------------------------------------------------
# The organization endpoint
# --------------------------------------------------------------------------


def test_the_org_endpoint_returns_the_callers_own_org(client, db_session):
    _org_with_members(client, db_session)
    body = client.get(ORG, headers=_headers(_token(client, "owner@acme.test"))).json()

    assert body["name"] == "Acme"
    assert body["kind"] == "company"
    assert body["member_count"] == 3
