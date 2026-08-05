"""Invitations end to end: mint, deliver, accept, refuse (P7.4).

An invitation is the only way to obtain a role in an organization you did not
create, so the tests that matter are the ones about the ways it could be
abused rather than the happy path:

* a token that reaches the wrong person must not become a different account
  (the invited address is authoritative, never the caller's);
* a Manager must not be able to mint Yanki staff by naming a platform role;
* a link must stop working when it is revoked, when it is used, and when it
  expires — and each of those must say something different to a person holding
  a genuine link, while an unknown token says nothing at all;
* an invitation to another organization must be invisible and unusable from
  this one.

The store-nothing property gets its own test: what is written to the database
must never be the token that was emailed.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import AuditEvent, Invitation, Membership, Organization, User
from app.services import invitations

SIGNUP = "/api/v1/auth/signup"
LOGIN = "/api/v1/auth/login"
INVITATIONS = "/api/v1/admin/invitations"
MEMBERS = "/api/v1/admin/members"
PASSWORD = "correct-horse-battery-staple"
NEW_PASSWORD = "another-perfectly-fine-password"


@pytest.fixture(autouse=True)
def auth_settings(client: TestClient) -> Iterator[None]:
    settings = Settings(
        jwt_secret_key=SecretStr("a" * 64),
        jwt_issuer="test-yanki-api",
        jwt_audience="test-yanki-web",
        auth_refresh_cookie_secure=False,
        public_base_url="https://yanki.test",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield
    app.dependency_overrides.pop(get_settings, None)


def _signup(client: TestClient, email: str, **extra) -> dict:
    response = client.post(SIGNUP, json={"email": email, "password": PASSWORD, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def _token(client: TestClient, email: str, password: str = PASSWORD) -> str:
    response = client.post(LOGIN, json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(token: str, org_id=None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id is not None:
        headers["X-Org-Id"] = str(org_id)
    return headers


def _owner_org(client: TestClient, db_session, name: str = "Acme") -> Organization:
    email = f"owner@{name.lower()}.test"
    _signup(client, email, account_type="organization", organization_name=name)
    org = db_session.scalar(sa.select(Organization).where(Organization.name == name))
    assert org is not None
    return org


def _invite(client: TestClient, token: str, email: str, role: str = "analyst") -> dict:
    response = client.post(
        INVITATIONS, headers=_headers(token), json={"email": email, "role": role}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _token_from(accept_url: str) -> str:
    return accept_url.rsplit("/", 1)[-1]


# --------------------------------------------------------------------------
# Creating
# --------------------------------------------------------------------------


def test_an_owner_can_invite_someone_and_gets_a_one_time_link(client, db_session):
    _owner_org(client, db_session)
    created = _invite(client, _token(client, "owner@acme.test"), "newbie@acme.test", "editor")

    assert created["invitation"]["email"] == "newbie@acme.test"
    assert created["invitation"]["role"] == "editor"
    assert created["invitation"]["status"] == "pending"
    assert created["invitation"]["expired"] is False
    assert created["accept_url"].startswith("https://yanki.test/invite/")
    # Email is off by default in every environment, and the API says so rather
    # than claiming a send that never happened.
    assert created["email_sent"] is False


def test_the_emailed_token_is_never_what_the_database_stores(client, db_session):
    _owner_org(client, db_session)
    created = _invite(client, _token(client, "owner@acme.test"), "newbie@acme.test")
    plaintext = _token_from(created["accept_url"])

    row = db_session.scalar(sa.select(Invitation))
    assert row is not None
    assert row.token_hash != plaintext
    assert row.token_hash == invitations.hash_token(plaintext)
    # And nothing anywhere in the row carries the plaintext.
    assert plaintext not in str(row.__dict__)


def test_the_listing_never_returns_a_token(client, db_session):
    _owner_org(client, db_session)
    owner = _token(client, "owner@acme.test")
    created = _invite(client, owner, "newbie@acme.test")
    plaintext = _token_from(created["accept_url"])

    body = client.get(INVITATIONS, headers=_headers(owner)).json()
    assert plaintext not in str(body)
    assert body["total"] == 1
    assert body["invitations"][0]["invited_by_email"] == "owner@acme.test"


def test_a_customer_cannot_invite_a_platform_role(client, db_session):
    _owner_org(client, db_session)
    response = client.post(
        INVITATIONS,
        headers=_headers(_token(client, "owner@acme.test")),
        json={"email": "spy@acme.test", "role": "super_admin"},
    )
    assert response.status_code == 422
    assert "super_admin" not in response.json()["detail"]


def test_inviting_an_existing_member_is_refused(client, db_session):
    org = _owner_org(client, db_session)
    _signup(client, "already@acme.test")
    user = db_session.scalar(sa.select(User).where(User.email == "already@acme.test"))
    db_session.add(Membership(org_id=org.id, user_id=user.id, role="viewer", status="active"))
    db_session.commit()

    response = client.post(
        INVITATIONS,
        headers=_headers(_token(client, "owner@acme.test")),
        json={"email": "already@acme.test", "role": "editor"},
    )
    assert response.status_code == 409
    assert "already a member" in response.json()["detail"]


def test_re_inviting_the_same_address_replaces_the_live_invitation(client, db_session):
    _owner_org(client, db_session)
    owner = _token(client, "owner@acme.test")
    first = _invite(client, owner, "twice@acme.test")
    second = _invite(client, owner, "twice@acme.test")

    # Exactly one pending row, and the first link no longer works — otherwise an
    # invitee would hold two valid credentials and revoking one would not help.
    pending = db_session.scalars(sa.select(Invitation).where(Invitation.status == "pending")).all()
    assert len(pending) == 1

    stale = client.get(f"/api/v1/invitations/{_token_from(first['accept_url'])}")
    assert stale.status_code == 410
    fresh = client.get(f"/api/v1/invitations/{_token_from(second['accept_url'])}")
    assert fresh.status_code == 200


def test_a_viewer_cannot_invite(client, db_session):
    org = _owner_org(client, db_session)
    _signup(client, "viewer@acme.test")
    user = db_session.scalar(sa.select(User).where(User.email == "viewer@acme.test"))
    db_session.add(Membership(org_id=org.id, user_id=user.id, role="viewer", status="active"))
    db_session.commit()

    response = client.post(
        INVITATIONS,
        headers=_headers(_token(client, "viewer@acme.test"), org_id=org.id),
        json={"email": "nope@acme.test", "role": "editor"},
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------
# Previewing
# --------------------------------------------------------------------------


def test_the_preview_says_what_is_being_joined(client, db_session):
    _owner_org(client, db_session)
    created = _invite(client, _token(client, "owner@acme.test"), "newbie@acme.test", "analyst")

    body = client.get(f"/api/v1/invitations/{_token_from(created['accept_url'])}").json()
    assert body == {
        "email": "newbie@acme.test",
        "role": "analyst",
        "organization_name": "Acme",
        "expires_at": body["expires_at"],
    }


def test_previewing_does_not_consume_the_invitation(client, db_session):
    _owner_org(client, db_session)
    created = _invite(client, _token(client, "owner@acme.test"), "newbie@acme.test")
    token = _token_from(created["accept_url"])

    # An email client's link prefetcher would otherwise burn the invitation
    # before the invitee ever clicked it.
    for _ in range(3):
        assert client.get(f"/api/v1/invitations/{token}").status_code == 200

    row = db_session.scalar(sa.select(Invitation))
    assert row.status == "pending"


def test_an_unknown_token_is_a_flat_404(client, db_session):
    response = client.get("/api/v1/invitations/" + "z" * 40)
    assert response.status_code == 404
    assert response.json()["detail"] == "That invitation link is not valid."


def test_an_expired_invitation_says_so(client, db_session):
    _owner_org(client, db_session)
    created = _invite(client, _token(client, "owner@acme.test"), "late@acme.test")

    row = db_session.scalar(sa.select(Invitation))
    row.expires_at = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()

    response = client.get(f"/api/v1/invitations/{_token_from(created['accept_url'])}")
    assert response.status_code == 410
    assert "expired" in response.json()["detail"].lower()


def test_a_revoked_invitation_says_so(client, db_session):
    _owner_org(client, db_session)
    owner = _token(client, "owner@acme.test")
    created = _invite(client, owner, "gone@acme.test")
    invitation_id = created["invitation"]["id"]

    revoked = client.delete(f"{INVITATIONS}/{invitation_id}", headers=_headers(owner))
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    response = client.get(f"/api/v1/invitations/{_token_from(created['accept_url'])}")
    assert response.status_code == 410
    assert "withdrawn" in response.json()["detail"].lower()


def test_a_suspended_organization_stops_accepting_members(client, db_session):
    org = _owner_org(client, db_session)
    created = _invite(client, _token(client, "owner@acme.test"), "newbie@acme.test")

    org = db_session.get(Organization, org.id)
    org.status = "suspended"
    db_session.commit()

    response = client.get(f"/api/v1/invitations/{_token_from(created['accept_url'])}")
    assert response.status_code == 410


# --------------------------------------------------------------------------
# Accepting
# --------------------------------------------------------------------------


def test_accepting_creates_the_account_with_the_invited_role(client, db_session):
    org = _owner_org(client, db_session)
    created = _invite(client, _token(client, "owner@acme.test"), "newbie@acme.test", "editor")

    response = client.post(
        f"/api/v1/invitations/{_token_from(created['accept_url'])}/accept",
        json={"password": NEW_PASSWORD},
    )
    assert response.status_code == 201, response.text
    assert response.json()["user"]["email"] == "newbie@acme.test"
    assert response.json()["access_token"]

    user = db_session.scalar(sa.select(User).where(User.email == "newbie@acme.test"))
    membership = db_session.scalar(
        sa.select(Membership).where(Membership.org_id == org.id, Membership.user_id == user.id)
    )
    assert membership.role == "editor"
    assert membership.status == "active"


def test_an_accepted_invitee_can_log_in_and_see_the_org(client, db_session):
    org = _owner_org(client, db_session)
    created = _invite(client, _token(client, "owner@acme.test"), "newbie@acme.test", "admin")
    client.post(
        f"/api/v1/invitations/{_token_from(created['accept_url'])}/accept",
        json={"password": NEW_PASSWORD},
    )

    token = _token(client, "newbie@acme.test", NEW_PASSWORD)
    me = client.get("/api/v1/auth/me", headers=_headers(token, org_id=org.id)).json()
    assert me["organization"]["name"] == "Acme"
    assert me["role"] == "admin"
    assert "member:invite" in me["permissions"]


def test_an_invitation_is_single_use(client, db_session):
    _owner_org(client, db_session)
    created = _invite(client, _token(client, "owner@acme.test"), "newbie@acme.test")
    url = f"/api/v1/invitations/{_token_from(created['accept_url'])}/accept"

    assert client.post(url, json={"password": NEW_PASSWORD}).status_code == 201
    second = client.post(url, json={"password": NEW_PASSWORD})
    assert second.status_code == 410
    assert "already been used" in second.json()["detail"]


def test_an_expired_invitation_cannot_be_accepted(client, db_session):
    _owner_org(client, db_session)
    created = _invite(client, _token(client, "owner@acme.test"), "late@acme.test")
    row = db_session.scalar(sa.select(Invitation))
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    response = client.post(
        f"/api/v1/invitations/{_token_from(created['accept_url'])}/accept",
        json={"password": NEW_PASSWORD},
    )
    assert response.status_code == 410
    assert db_session.scalar(sa.select(User).where(User.email == "late@acme.test")) is None


def test_an_existing_account_must_sign_in_before_accepting(client, db_session):
    _owner_org(client, db_session)
    _signup(client, "already@other.test")
    created = _invite(client, _token(client, "owner@acme.test"), "already@other.test")

    # Accepting anonymously with a NEW password would be an account takeover by
    # anyone who intercepted the link.
    response = client.post(
        f"/api/v1/invitations/{_token_from(created['accept_url'])}/accept",
        json={"password": "a-brand-new-password"},
    )
    assert response.status_code == 409
    assert "Sign in first" in response.json()["detail"]

    # The password is unchanged: the original still works.
    assert _token(client, "already@other.test")


def test_a_signed_in_invitee_joins_without_a_new_account(client, db_session):
    org = _owner_org(client, db_session)
    _signup(client, "contractor@other.test")
    created = _invite(client, _token(client, "owner@acme.test"), "contractor@other.test", "analyst")

    response = client.post(
        f"/api/v1/invitations/{_token_from(created['accept_url'])}/accept",
        headers=_headers(_token(client, "contractor@other.test")),
        json={"password": "ignored-but-required-by-the-schema"},
    )
    assert response.status_code == 201

    users = db_session.scalars(sa.select(User).where(User.email == "contractor@other.test")).all()
    assert len(users) == 1
    # Two memberships now — their own personal org and the one they joined.
    memberships = db_session.scalars(
        sa.select(Membership).where(Membership.user_id == users[0].id)
    ).all()
    assert len(memberships) == 2
    assert org.id in {m.org_id for m in memberships}
    assert next(m.role for m in memberships if m.org_id == org.id) == "analyst"
    # And their existing password still works: accepting is not a reset.
    assert _token(client, "contractor@other.test")


def test_accepting_cannot_be_redirected_to_another_address(client, db_session):
    _owner_org(client, db_session)
    created = _invite(client, _token(client, "owner@acme.test"), "intended@acme.test")

    # There is no field to try: the account is created with the invitation's
    # address, so an extra key in the body changes nothing.
    response = client.post(
        f"/api/v1/invitations/{_token_from(created['accept_url'])}/accept",
        json={"password": NEW_PASSWORD, "email": "attacker@evil.test"},
    )
    assert response.status_code == 201
    assert response.json()["user"]["email"] == "intended@acme.test"
    assert db_session.scalar(sa.select(User).where(User.email == "attacker@evil.test")) is None


def test_a_short_password_is_refused_before_the_invitation_is_consumed(client, db_session):
    _owner_org(client, db_session)
    created = _invite(client, _token(client, "owner@acme.test"), "newbie@acme.test")

    response = client.post(
        f"/api/v1/invitations/{_token_from(created['accept_url'])}/accept",
        json={"password": "short"},
    )
    assert response.status_code == 422
    assert db_session.scalar(sa.select(Invitation)).status == "pending"


# --------------------------------------------------------------------------
# Resending and revoking
# --------------------------------------------------------------------------


def test_resending_invalidates_the_previous_link(client, db_session):
    _owner_org(client, db_session)
    owner = _token(client, "owner@acme.test")
    created = _invite(client, owner, "newbie@acme.test")
    old_token = _token_from(created["accept_url"])

    resent = client.post(
        f"{INVITATIONS}/{created['invitation']['id']}/resend", headers=_headers(owner)
    )
    assert resent.status_code == 200
    new_token = _token_from(resent.json()["accept_url"])
    assert new_token != old_token
    assert resent.json()["invitation"]["sent_count"] == 2

    assert client.get(f"/api/v1/invitations/{old_token}").status_code == 404
    assert client.get(f"/api/v1/invitations/{new_token}").status_code == 200


def test_resending_revives_an_expired_invitation(client, db_session):
    _owner_org(client, db_session)
    owner = _token(client, "owner@acme.test")
    created = _invite(client, owner, "late@acme.test")
    row = db_session.scalar(sa.select(Invitation))
    row.expires_at = datetime.now(UTC) - timedelta(days=3)
    db_session.commit()

    resent = client.post(
        f"{INVITATIONS}/{created['invitation']['id']}/resend", headers=_headers(owner)
    )
    assert resent.status_code == 200
    assert resent.json()["invitation"]["expired"] is False
    assert (
        client.get(f"/api/v1/invitations/{_token_from(resent.json()['accept_url'])}").status_code
        == 200
    )


def test_an_accepted_invitation_cannot_be_revoked(client, db_session):
    _owner_org(client, db_session)
    owner = _token(client, "owner@acme.test")
    created = _invite(client, owner, "newbie@acme.test")
    client.post(
        f"/api/v1/invitations/{_token_from(created['accept_url'])}/accept",
        json={"password": NEW_PASSWORD},
    )

    # Saying "done" here would let an administrator believe they removed access
    # they did not remove. The seat exists; removing it is a membership change.
    response = client.delete(
        f"{INVITATIONS}/{created['invitation']['id']}", headers=_headers(owner)
    )
    assert response.status_code == 409
    assert "remove the member instead" in response.json()["detail"]


# --------------------------------------------------------------------------
# Isolation
# --------------------------------------------------------------------------


def test_one_orgs_invitations_are_invisible_to_another(client, db_session):
    _owner_org(client, db_session, "Acme")
    _owner_org(client, db_session, "Globex")
    _invite(client, _token(client, "owner@acme.test"), "acme-invitee@acme.test")

    body = client.get(INVITATIONS, headers=_headers(_token(client, "owner@globex.test"))).json()
    assert body["total"] == 0


def test_revoking_another_orgs_invitation_is_a_404(client, db_session):
    _owner_org(client, db_session, "Acme")
    _owner_org(client, db_session, "Globex")
    created = _invite(client, _token(client, "owner@acme.test"), "acme-invitee@acme.test")

    response = client.delete(
        f"{INVITATIONS}/{created['invitation']['id']}",
        headers=_headers(_token(client, "owner@globex.test")),
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------


def test_the_whole_invitation_lifecycle_is_audited(client, db_session):
    _owner_org(client, db_session)
    owner = _token(client, "owner@acme.test")
    created = _invite(client, owner, "newbie@acme.test")
    client.post(f"{INVITATIONS}/{created['invitation']['id']}/resend", headers=_headers(owner))
    resent = client.post(
        f"{INVITATIONS}/{created['invitation']['id']}/resend", headers=_headers(owner)
    )
    client.post(
        f"/api/v1/invitations/{_token_from(resent.json()['accept_url'])}/accept",
        json={"password": NEW_PASSWORD},
    )

    actions = db_session.scalars(
        sa.select(AuditEvent.action).where(AuditEvent.entity_type == "invitation")
    ).all()
    assert "invitation:create" in actions
    assert "invitation:resend" in actions
    assert "invitation:accept" in actions


def test_re_inviting_a_deactivated_member_reactivates_their_seat(db_session):
    """A returning colleague gets their row back, never a second one.

    The unique constraint on (org, user) would refuse a duplicate anyway; what
    this proves is that the invitation path notices, applies the newly invited
    role, and flips the membership back to active.
    """

    user = User(email="back@acme.test", password_hash="x")
    org = Organization(name="Acme", slug="acme", kind="company", status="active")
    db_session.add_all([user, org])
    db_session.flush()
    db_session.add(Membership(org_id=org.id, user_id=user.id, role="viewer", status="deactivated"))
    db_session.commit()

    minted = invitations.create_invitation(
        db_session,
        org_id=org.id,
        email="back@acme.test",
        role="editor",
        invited_by_user_id=None,
    )
    invitations.redeem(db_session, invitation=minted.invitation, user=user)
    db_session.commit()

    memberships = db_session.scalars(
        sa.select(Membership).where(Membership.user_id == user.id)
    ).all()
    assert len(memberships) == 1
    assert memberships[0].role == "editor"
    assert memberships[0].status == "active"
