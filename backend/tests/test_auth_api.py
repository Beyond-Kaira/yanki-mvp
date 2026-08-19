"""API tests for email/password and JWT authentication."""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth_cookies import REFRESH_COOKIE_PATH
from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import AuditEvent, AuthSession, Membership, Organization, User
from app.services.auth import verify_password
from app.services.tokens import (
    TokenType,
    decode_token,
    hash_refresh_jti,
)

SIGNUP_URL = "/api/v1/auth/signup"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"
ME_URL = "/api/v1/auth/me"
SESSIONS_URL = "/api/v1/auth/sessions"
REVOKE_ALL_URL = "/api/v1/auth/sessions/revoke-all"


@pytest.fixture()
def auth_settings() -> Settings:
    """Return isolated JWT settings suitable for HTTP tests."""

    return Settings(
        jwt_secret_key=SecretStr("a" * 64),
        jwt_issuer="test-yanki-api",
        jwt_audience="test-yanki-web",
        jwt_access_token_minutes=15,
        jwt_refresh_token_days=30,
        jwt_clock_skew_seconds=0,
        # TestClient uses http://testserver, so Secure cookies would not be sent.
        auth_refresh_cookie_secure=False,
    )


@pytest.fixture(autouse=True)
def override_auth_settings(
    client: TestClient,
    auth_settings: Settings,
) -> Iterator[None]:
    """Override only JWT configuration for tests in this module."""

    def override_get_settings() -> Settings:
        return auth_settings

    app.dependency_overrides[get_settings] = override_get_settings

    try:
        yield
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_signup_creates_user_with_normalized_email_and_hashed_password(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.post(
        SIGNUP_URL,
        json={
            "email": "  Test@Example.COM  ",
            "password": "correct-horse",
        },
    )

    assert response.status_code == 201

    body = response.json()
    assert body["email"] == "test@example.com"
    assert set(body) == {"id", "email", "created_at"}

    user = db_session.scalar(
        select(User).where(
            User.email == "test@example.com",
        ),
    )

    assert user is not None
    assert user.password_hash != "correct-horse"
    assert verify_password(
        "correct-horse",
        user.password_hash,
    )


def test_signup_rejects_duplicate_normalized_email(
    client: TestClient,
    db_session: Session,
) -> None:
    first_response = client.post(
        SIGNUP_URL,
        json={
            "email": "test@example.com",
            "password": "correct-horse",
        },
    )
    duplicate_response = client.post(
        SIGNUP_URL,
        json={
            "email": " TEST@example.com ",
            "password": "another-password",
        },
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert duplicate_response.json() == {
        "detail": "email already registered",
    }

    user_count = db_session.scalar(
        select(func.count()).select_from(User),
    )
    assert user_count == 1


def test_login_returns_access_token_and_sets_refresh_cookie(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    user_body = _signup(client)

    login_response = client.post(
        LOGIN_URL,
        json={
            "email": " TEST@EXAMPLE.COM ",
            "password": "correct-horse",
        },
    )

    assert login_response.status_code == 200

    body = login_response.json()

    assert set(body) == {
        "user",
        "access_token",
        "token_type",
    }
    assert body["user"]["email"] == "test@example.com"
    assert set(body["user"]) == {
        "id",
        "email",
        "created_at",
    }
    assert isinstance(body["access_token"], str)
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert "refresh_token" not in body

    refresh_token = login_response.cookies.get(
        auth_settings.auth_refresh_cookie_name,
    )

    assert refresh_token is not None
    assert refresh_token not in body.values()

    set_cookie_header = login_response.headers["set-cookie"].lower()

    assert "httponly" in set_cookie_header
    assert "samesite=lax" in set_cookie_header
    assert f"path={REFRESH_COOKIE_PATH}" in set_cookie_header

    access_claims = decode_token(
        body["access_token"],
        expected_type=TokenType.ACCESS,
        settings=auth_settings,
    )
    refresh_claims = decode_token(
        refresh_token,
        expected_type=TokenType.REFRESH,
        settings=auth_settings,
    )

    assert str(access_claims.user_id) == user_body["id"]
    assert refresh_claims.user_id == access_claims.user_id

    auth_session = db_session.scalar(
        select(AuthSession).where(
            AuthSession.refresh_jti_hash
            == hash_refresh_jti(
                refresh_claims.jti,
                settings=auth_settings,
            ),
        ),
    )

    assert auth_session is not None
    assert auth_session.user_id == access_claims.user_id
    assert auth_session.consumed_at is None
    assert auth_session.revoked_at is None


def test_login_rejects_wrong_password_and_unknown_email(
    client: TestClient,
    db_session: Session,
) -> None:
    _signup(client)

    wrong_password_response = client.post(
        LOGIN_URL,
        json={
            "email": "test@example.com",
            "password": "wrong-password",
        },
    )
    unknown_email_response = client.post(
        LOGIN_URL,
        json={
            "email": "unknown@example.com",
            "password": "wrong-password",
        },
    )

    expected_error = {
        "detail": "invalid email or password",
    }

    assert wrong_password_response.status_code == 401
    assert wrong_password_response.json() == expected_error

    assert unknown_email_response.status_code == 401
    assert unknown_email_response.json() == expected_error

    session_count = db_session.scalar(
        select(func.count()).select_from(AuthSession),
    )
    assert session_count == 0


def test_auth_request_validation(
    client: TestClient,
) -> None:
    invalid_email_response = client.post(
        SIGNUP_URL,
        json={
            "email": "not-an-email",
            "password": "correct-horse",
        },
    )
    short_password_response = client.post(
        SIGNUP_URL,
        json={
            "email": "test@example.com",
            "password": "short",
        },
    )
    empty_login_password_response = client.post(
        LOGIN_URL,
        json={
            "email": "test@example.com",
            "password": "",
        },
    )

    assert invalid_email_response.status_code == 422
    assert short_password_response.status_code == 422
    assert empty_login_password_response.status_code == 422


def test_me_returns_user_for_valid_access_token(
    client: TestClient,
) -> None:
    user_body = _signup(client)
    login_body, _ = _login(client)

    response = client.get(
        ME_URL,
        headers={
            "Authorization": f"Bearer {login_body['access_token']}",
        },
    )

    assert response.status_code == 200
    body = response.json()

    # The identity fields still match the signup response exactly — this part
    # of the contract is unchanged.
    for field in ("id", "email", "created_at"):
        assert body[field] == user_body[field]

    # And /me now additionally carries what the UI needs to render authority
    # without a second round trip: the org, the caller's role in it, and the
    # permission list. Enforcement stays server-side — this is for rendering.
    assert body["status"] == "active"
    assert body["organization"]["kind"] == "personal"
    assert body["role"] == "owner"
    assert "project:read" in body["permissions"]


def test_me_rejects_missing_token_and_refresh_token(
    client: TestClient,
    auth_settings: Settings,
) -> None:
    _signup(client)
    _, refresh_token = _login(
        client,
        auth_settings=auth_settings,
    )

    missing_response = client.get(ME_URL)
    refresh_as_bearer_response = client.get(
        ME_URL,
        headers={
            "Authorization": f"Bearer {refresh_token}",
        },
    )

    expected_error = {
        "detail": "invalid or missing access token",
    }

    assert missing_response.status_code == 401
    assert missing_response.json() == expected_error
    assert missing_response.headers["www-authenticate"] == "Bearer"

    assert refresh_as_bearer_response.status_code == 401
    assert refresh_as_bearer_response.json() == expected_error


def test_refresh_rotates_cookie_and_access_token(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    _signup(client)
    login_body, original_refresh_token = _login(
        client,
        auth_settings=auth_settings,
    )

    original_refresh_claims = decode_token(
        original_refresh_token,
        expected_type=TokenType.REFRESH,
        settings=auth_settings,
    )

    refresh_response = client.post(REFRESH_URL)

    assert refresh_response.status_code == 200

    refresh_body = refresh_response.json()

    assert set(refresh_body) == {
        "access_token",
        "token_type",
    }
    assert refresh_body["token_type"] == "bearer"
    assert refresh_body["access_token"] != login_body["access_token"]
    assert "refresh_token" not in refresh_body

    rotated_refresh_token = refresh_response.cookies.get(
        auth_settings.auth_refresh_cookie_name,
    )

    assert rotated_refresh_token is not None
    assert rotated_refresh_token != original_refresh_token

    rotated_refresh_claims = decode_token(
        rotated_refresh_token,
        expected_type=TokenType.REFRESH,
        settings=auth_settings,
    )
    rotated_access_claims = decode_token(
        refresh_body["access_token"],
        expected_type=TokenType.ACCESS,
        settings=auth_settings,
    )

    assert rotated_refresh_claims.user_id == original_refresh_claims.user_id
    assert rotated_access_claims.user_id == original_refresh_claims.user_id
    assert rotated_refresh_claims.expires_at == original_refresh_claims.expires_at

    original_hash = hash_refresh_jti(
        original_refresh_claims.jti,
        settings=auth_settings,
    )
    rotated_hash = hash_refresh_jti(
        rotated_refresh_claims.jti,
        settings=auth_settings,
    )

    db_session.expire_all()

    original_session = db_session.scalar(
        select(AuthSession).where(
            AuthSession.refresh_jti_hash == original_hash,
        ),
    )
    successor_session = db_session.scalar(
        select(AuthSession).where(
            AuthSession.refresh_jti_hash == rotated_hash,
        ),
    )

    assert original_session is not None
    assert successor_session is not None
    assert original_session.consumed_at is not None
    assert original_session.replaced_by_id == successor_session.id
    assert successor_session.consumed_at is None
    assert successor_session.revoked_at is None
    assert successor_session.family_id == original_session.family_id


def test_reusing_old_refresh_token_revokes_family(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    _signup(client)
    _, original_refresh_token = _login(
        client,
        auth_settings=auth_settings,
    )

    rotation_response = client.post(REFRESH_URL)

    assert rotation_response.status_code == 200

    rotated_refresh_token = rotation_response.cookies.get(
        auth_settings.auth_refresh_cookie_name,
    )
    assert rotated_refresh_token is not None

    original_claims = decode_token(
        original_refresh_token,
        expected_type=TokenType.REFRESH,
        settings=auth_settings,
    )

    client.cookies.clear()
    client.cookies.set(
        auth_settings.auth_refresh_cookie_name,
        original_refresh_token,
        path=REFRESH_COOKIE_PATH,
    )

    reuse_response = client.post(REFRESH_URL)

    assert reuse_response.status_code == 401
    assert reuse_response.json() == {
        "detail": "invalid or missing refresh token",
    }

    client.cookies.clear()
    client.cookies.set(
        auth_settings.auth_refresh_cookie_name,
        rotated_refresh_token,
        path=REFRESH_COOKIE_PATH,
    )

    successor_response = client.post(REFRESH_URL)

    assert successor_response.status_code == 401

    original_hash = hash_refresh_jti(
        original_claims.jti,
        settings=auth_settings,
    )

    db_session.expire_all()

    original_session = db_session.scalar(
        select(AuthSession).where(
            AuthSession.refresh_jti_hash == original_hash,
        ),
    )

    assert original_session is not None

    family_rows = list(
        db_session.scalars(
            select(AuthSession).where(
                AuthSession.family_id == original_session.family_id,
            ),
        ),
    )

    assert len(family_rows) == 2
    assert all(row.revoked_at is not None for row in family_rows)


def test_logout_revokes_current_family_and_clears_cookie(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    _signup(client)
    _, refresh_token = _login(
        client,
        auth_settings=auth_settings,
    )

    refresh_claims = decode_token(
        refresh_token,
        expected_type=TokenType.REFRESH,
        settings=auth_settings,
    )
    refresh_hash = hash_refresh_jti(
        refresh_claims.jti,
        settings=auth_settings,
    )

    logout_response = client.post(LOGOUT_URL)

    assert logout_response.status_code == 204
    assert logout_response.content == b""
    assert (
        client.cookies.get(
            auth_settings.auth_refresh_cookie_name,
        )
        is None
    )

    db_session.expire_all()

    auth_session = db_session.scalar(
        select(AuthSession).where(
            AuthSession.refresh_jti_hash == refresh_hash,
        ),
    )

    assert auth_session is not None
    assert auth_session.revoked_at is not None

    client.cookies.set(
        auth_settings.auth_refresh_cookie_name,
        refresh_token,
        path=REFRESH_COOKIE_PATH,
    )

    refresh_response = client.post(REFRESH_URL)

    assert refresh_response.status_code == 401


def test_refresh_rejects_missing_cookie(
    client: TestClient,
) -> None:
    client.cookies.clear()

    response = client.post(REFRESH_URL)

    assert response.status_code == 401
    assert response.json() == {
        "detail": "invalid or missing refresh token",
    }


# ---------------------------------------------------------------------------
# Multi-org /auth/me and self-service session management (P7.5)
# ---------------------------------------------------------------------------


def _add_membership(
    db_session: Session,
    *,
    user_id: uuid.UUID,
    name: str,
    slug: str,
    role: str = "admin",
    kind: str = "company",
) -> Organization:
    """Give ``user_id`` a second organization, as accepting an invitation does."""

    org = Organization(
        name=name,
        slug=slug,
        kind=kind,
        status="active",
        owner_user_id=user_id,
    )
    db_session.add(org)
    db_session.flush()
    db_session.add(
        Membership(org_id=org.id, user_id=user_id, role=role, status="active"),
    )
    db_session.commit()
    return org


def test_me_still_returns_singular_org_and_adds_the_full_list(
    client: TestClient,
) -> None:
    """The contract's singular fields are untouched; the list is purely additive."""

    _signup(client)
    login_body, _ = _login(client)

    body = client.get(
        ME_URL,
        headers={"Authorization": f"Bearer {login_body['access_token']}"},
    ).json()

    # The pre-existing singular fields still say exactly what they said before.
    assert body["organization"]["kind"] == "personal"
    assert body["role"] == "owner"
    assert "project:read" in body["permissions"]

    # And the new list carries the caller's memberships — one, for a solo user —
    # each with the caller's role in that org.
    assert [org["role"] for org in body["organizations"]] == ["owner"]
    assert body["organizations"][0]["id"] == body["organization"]["id"]


def test_me_lists_every_org_and_switches_by_header(
    client: TestClient,
    db_session: Session,
) -> None:
    """A user who joined a second org can reach it — the defect this card closes."""

    user_body = _signup(client)
    login_body, _ = _login(client)
    bearer = {"Authorization": f"Bearer {login_body['access_token']}"}

    second = _add_membership(
        db_session,
        user_id=uuid.UUID(user_body["id"]),
        name="Acme Co",
        slug="acme-co",
        role="admin",
    )

    default_me = client.get(ME_URL, headers=bearer).json()
    # With no header the singular fields still resolve to the FIRST org, exactly
    # as before — additive, not a behaviour change.
    assert default_me["organization"]["kind"] == "personal"
    assert default_me["role"] == "owner"
    orgs = {org["id"]: org for org in default_me["organizations"]}
    assert len(orgs) == 2
    assert orgs[str(second.id)]["role"] == "admin"
    assert orgs[str(second.id)]["name"] == "Acme Co"

    # Naming the second org in X-Org-Id makes the singular fields describe it —
    # this is what a switch does, and without it the second org is unreachable.
    switched = client.get(ME_URL, headers={**bearer, "X-Org-Id": str(second.id)}).json()
    assert switched["organization"]["id"] == str(second.id)
    assert switched["role"] == "admin"
    assert len(switched["organizations"]) == 2


def test_me_falls_back_when_org_header_is_not_the_callers(
    client: TestClient,
) -> None:
    """A stale or forged X-Org-Id degrades to the default org, never a 403 here."""

    _signup(client)
    login_body, _ = _login(client)

    resp = client.get(
        ME_URL,
        headers={
            "Authorization": f"Bearer {login_body['access_token']}",
            "X-Org-Id": str(uuid.uuid4()),
        },
    )

    assert resp.status_code == 200
    assert resp.json()["organization"]["kind"] == "personal"


def test_sessions_lists_only_the_current_session_and_flags_it(
    client: TestClient,
) -> None:
    _signup(client)
    login_body, _ = _login(client)

    resp = client.get(
        SESSIONS_URL,
        headers={"Authorization": f"Bearer {login_body['access_token']}"},
    )

    assert resp.status_code == 200
    sessions = resp.json()["sessions"]
    assert len(sessions) == 1

    only = sessions[0]
    assert only["current"] is True
    # Nothing replayable leaves the endpoint: the shape is exactly these fields,
    # and in particular there is no refresh_jti_hash and no token.
    assert set(only) == {"id", "created_at", "last_active_at", "expires_at", "current"}


def test_sessions_are_scoped_to_the_caller(
    client: TestClient,
) -> None:
    _signup(client, email="a@example.com")
    a_login, _ = _login(client, email="a@example.com")
    a_bearer = {"Authorization": f"Bearer {a_login['access_token']}"}
    a_sessions = client.get(SESSIONS_URL, headers=a_bearer).json()["sessions"]
    a_family = a_sessions[0]["id"]

    # A second user logging in on the same client must not see A's session.
    _signup(client, email="b@example.com")
    b_login, _ = _login(client, email="b@example.com")
    b_bearer = {"Authorization": f"Bearer {b_login['access_token']}"}
    b_families = {s["id"] for s in client.get(SESSIONS_URL, headers=b_bearer).json()["sessions"]}

    assert a_family not in b_families


def test_revoke_rejects_another_users_session_without_leaking_existence(
    client: TestClient,
) -> None:
    _signup(client, email="a@example.com")
    a_login, _ = _login(client, email="a@example.com")
    a_bearer = {"Authorization": f"Bearer {a_login['access_token']}"}
    a_family = client.get(SESSIONS_URL, headers=a_bearer).json()["sessions"][0]["id"]

    _signup(client, email="b@example.com")
    b_login, _ = _login(client, email="b@example.com")
    b_bearer = {"Authorization": f"Bearer {b_login['access_token']}"}

    real = client.delete(f"{SESSIONS_URL}/{a_family}", headers=b_bearer)
    fake = client.delete(f"{SESSIONS_URL}/{uuid.uuid4()}", headers=b_bearer)

    # A real-but-not-yours id and a made-up id answer identically, so revocation
    # cannot be used to probe for the existence of another user's session ids.
    assert real.status_code == 404
    assert fake.status_code == 404
    assert real.json() == fake.json()

    # And A's session was not touched.
    a_after = {s["id"] for s in client.get(SESSIONS_URL, headers=a_bearer).json()["sessions"]}
    assert a_after == {a_family}


def test_revoke_own_session_revokes_family_and_writes_audit(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    _signup(client)
    login_body, refresh_token = _login(client, auth_settings=auth_settings)
    bearer = {"Authorization": f"Bearer {login_body['access_token']}"}

    family = client.get(SESSIONS_URL, headers=bearer).json()["sessions"][0]["id"]

    revoke = client.delete(f"{SESSIONS_URL}/{family}", headers=bearer)
    assert revoke.status_code == 204

    # The family is genuinely revoked: its refresh token can no longer rotate.
    client.cookies.set(
        auth_settings.auth_refresh_cookie_name,
        refresh_token,
        path=REFRESH_COOKIE_PATH,
    )
    assert client.post(REFRESH_URL).status_code == 401

    db_session.expire_all()
    event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.action == "auth:session_revoke"),
    )
    assert event is not None
    assert event.actor_type == "user"
    assert str(event.entity_id) == family


def test_revoke_all_keeps_current_signs_out_others_and_audits(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    _signup(client)
    # Two logins for the same user are two families — two "devices". The second
    # login's cookie is the one the client now carries, so it is the current one.
    _login(client, auth_settings=auth_settings)
    second_login, _ = _login(client, auth_settings=auth_settings)
    bearer = {"Authorization": f"Bearer {second_login['access_token']}"}

    before = client.get(SESSIONS_URL, headers=bearer).json()["sessions"]
    assert len(before) == 2
    assert sum(1 for s in before if s["current"]) == 1

    resp = client.post(REVOKE_ALL_URL, headers=bearer)
    assert resp.status_code == 200
    assert resp.json() == {"revoked": 1, "kept_current": True}

    after = client.get(SESSIONS_URL, headers=bearer).json()["sessions"]
    assert len(after) == 1
    assert after[0]["current"] is True

    # The kept session still works.
    assert client.post(REFRESH_URL).status_code == 200

    db_session.expire_all()
    event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.action == "auth:session_revoke_all"),
    )
    assert event is not None
    assert event.detail["devices_signed_out"] == 1
    assert event.detail["kept_current"] is True


def _signup(
    client: TestClient,
    *,
    email: str = "test@example.com",
    password: str = "correct-horse",
) -> dict[str, Any]:
    response = client.post(
        SIGNUP_URL,
        json={
            "email": email,
            "password": password,
        },
    )

    assert response.status_code == 201

    return response.json()


def _login(
    client: TestClient,
    *,
    auth_settings: Settings | None = None,
    email: str = "test@example.com",
    password: str = "correct-horse",
) -> tuple[dict[str, Any], str]:
    response = client.post(
        LOGIN_URL,
        json={
            "email": email,
            "password": password,
        },
    )

    assert response.status_code == 200

    settings = auth_settings or Settings(
        jwt_secret_key=SecretStr("a" * 64),
        jwt_issuer="test-yanki-api",
        jwt_audience="test-yanki-web",
        jwt_clock_skew_seconds=0,
        auth_refresh_cookie_secure=False,
    )

    refresh_token = response.cookies.get(
        settings.auth_refresh_cookie_name,
    )

    assert refresh_token is not None

    return response.json(), refresh_token


# --------------------------------------------------------------------------
# The password policy at the signup boundary
# --------------------------------------------------------------------------
#
# The rules themselves are tested in test_password_policy.py. What is asserted
# here is that the endpoint actually consults them, answers in a shape a client
# can use, and creates nothing when it refuses.


def test_signup_refuses_a_password_the_policy_rejects(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.post(
        SIGNUP_URL,
        json={"email": "new@example.com", "password": "password123456"},
    )

    assert response.status_code == 422

    body = response.json()
    assert "common" in body["rules"]
    assert isinstance(body["detail"], str)

    # Nothing was created, and in particular no organization: a refused signup
    # that left a half-provisioned tenant behind would be worse than one that
    # succeeded.
    assert db_session.scalar(select(User).where(User.email == "new@example.com")) is None


def test_signup_refuses_a_password_built_from_the_email(
    client: TestClient,
) -> None:
    """The context the route passes is the point of this one — the policy
    cannot apply a rule it is not given the material for."""

    response = client.post(
        SIGNUP_URL,
        json={"email": "kahvemasa@example.com", "password": "kahvemasa-2026"},
    )

    assert response.status_code == 422
    assert "context" in response.json()["rules"]


def test_signup_refuses_a_password_built_from_the_organization_name(
    client: TestClient,
) -> None:
    response = client.post(
        SIGNUP_URL,
        json={
            "email": "someone@example.com",
            "password": "bulutbilisim-1",
            "account_type": "organization",
            "organization_name": "Bulut Bilişim",
        },
    )

    assert response.status_code == 422
    assert "context" in response.json()["rules"]


def test_the_refusal_never_echoes_the_password(
    client: TestClient,
) -> None:
    """A 422 body is rendered in a browser and may be logged by anything in
    front of it."""

    secret = "password123456"
    response = client.post(
        SIGNUP_URL,
        json={"email": "new@example.com", "password": secret},
    )

    assert secret not in response.text


def test_signup_accepts_a_long_passphrase_with_no_composition_rule(
    client: TestClient,
) -> None:
    """All lowercase, no digit, no symbol — and correct. This is the test that
    fails if somebody 'strengthens' the policy back into a composition rule."""

    response = client.post(
        SIGNUP_URL,
        json={"email": "new@example.com", "password": "bulutkahvemasa"},
    )

    assert response.status_code == 201


def test_login_never_applies_the_policy(
    client: TestClient,
) -> None:
    """An account whose password predates the policy must still be able to sign
    in, and a guesser must not be told what the rules are. Both follow from the
    login path never consulting the policy — so a password that signup would
    refuse has to reach the credential check and fail THERE, as a 401.
    """

    _signup(client, email="old@example.com", password="correct-horse-battery")

    response = client.post(
        LOGIN_URL,
        json={"email": "old@example.com", "password": "password123456"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid email or password"}
