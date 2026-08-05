"""API tests for email/password and JWT authentication."""

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
from app.db.models import AuthSession, User
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
