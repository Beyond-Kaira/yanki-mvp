"""API tests for Google / Apple identity sign-in.

The tokens here are real RS256 JWTs signed with a key pair generated for the
test, and only the key *fetch* is stubbed — the provider's JWKS endpoint is the
one thing a hermetic suite cannot reach. Everything that decides whether a
sign-in is allowed (signature, audience, issuer, expiry, verified email) runs
exactly as it does in production, which is the point: a test that stubbed the
verification itself would prove nothing about the checks that matter.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import User
from app.services import oauth
from app.services.auth import create_user

OAUTH_URL = "/api/v1/auth/oauth"
GOOGLE_CLIENT_ID = "test-google-client.apps.googleusercontent.com"
GOOGLE_ISSUER = "https://accounts.google.com"


@pytest.fixture(scope="module")
def signing_key() -> Any:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture()
def oauth_settings() -> Settings:
    return Settings(
        jwt_secret_key=SecretStr("a" * 64),
        jwt_issuer="test-yanki-api",
        jwt_audience="test-yanki-web",
        jwt_clock_skew_seconds=0,
        # TestClient uses http://testserver, so Secure cookies would not be sent.
        auth_refresh_cookie_secure=False,
        google_client_id=GOOGLE_CLIENT_ID,
    )


@pytest.fixture(autouse=True)
def override_oauth_settings(
    client: TestClient,
    oauth_settings: Settings,
) -> Iterator[None]:
    app.dependency_overrides[get_settings] = lambda: oauth_settings
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_settings, None)


@pytest.fixture(autouse=True)
def stub_provider_keys(monkeypatch: pytest.MonkeyPatch, signing_key: Any) -> None:
    """Serve the test's own public key instead of fetching the provider's."""

    public_key = signing_key.public_key()

    class _StubClient:
        def get_signing_key_from_jwt(self, token: str) -> Any:
            return type("_Key", (), {"key": public_key})()

    monkeypatch.setattr(oauth, "_jwk_client", lambda jwks_uri: _StubClient())


@pytest.fixture()
def id_token(signing_key: Any):
    private_pem = signing_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    def _make(**overrides: Any) -> str:
        now = datetime.now(UTC)
        claims: dict[str, Any] = {
            "iss": GOOGLE_ISSUER,
            "aud": GOOGLE_CLIENT_ID,
            "sub": "104829371829301827364",
            "email": "ali@example.com",
            "email_verified": True,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        }
        claims.update(overrides)
        return jwt.encode(claims, private_pem, algorithm="RS256")

    return _make


def _sign_in(client: TestClient, token: str, **body: Any):
    return client.post(OAUTH_URL, json={"provider": "google", "id_token": token, **body})


def test_first_sign_in_creates_the_account_and_a_session(
    client: TestClient,
    db_session: Session,
    id_token: Any,
    oauth_settings: Settings,
) -> None:
    response = _sign_in(client, id_token())

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert oauth_settings.auth_refresh_cookie_name in response.cookies

    user = db_session.scalar(select(User).where(User.email == "ali@example.com"))
    assert user is not None
    assert user.auth_provider == "google"
    assert user.auth_subject == "104829371829301827364"
    # Nothing to sign in with by password, and no placeholder pretending there is.
    assert user.password_hash is None


def test_second_sign_in_reuses_the_same_account(
    client: TestClient,
    db_session: Session,
    id_token: Any,
) -> None:
    first = _sign_in(client, id_token())
    second = _sign_in(client, id_token())

    assert second.status_code == 200
    assert second.json()["user"]["id"] == first.json()["user"]["id"]
    assert db_session.scalar(select(func.count()).select_from(User)) == 1


def test_sign_in_links_an_existing_password_account_by_email(
    client: TestClient,
    db_session: Session,
    id_token: Any,
) -> None:
    existing = create_user(db_session, email="ali@example.com", password="hunter2hunter2")

    response = _sign_in(client, id_token())

    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(existing.id)
    db_session.expire_all()
    linked = db_session.get(User, existing.id)
    assert linked is not None
    assert linked.auth_subject == "104829371829301827364"
    # Linking must not cost them the password they already had.
    assert linked.password_hash is not None
    assert db_session.scalar(select(func.count()).select_from(User)) == 1


def test_sign_in_follows_an_email_change_at_the_provider(
    client: TestClient,
    db_session: Session,
    id_token: Any,
) -> None:
    first = _sign_in(client, id_token())

    moved = _sign_in(client, id_token(email="ali@company.example"))

    assert moved.status_code == 200
    assert moved.json()["user"]["id"] == first.json()["user"]["id"]
    assert db_session.scalar(select(func.count()).select_from(User)) == 1


def test_token_for_another_application_is_rejected(
    client: TestClient,
    db_session: Session,
    id_token: Any,
) -> None:
    response = _sign_in(client, id_token(aud="somebody-elses-client-id"))

    assert response.status_code == 401
    assert db_session.scalar(select(func.count()).select_from(User)) == 0


def test_unverified_email_is_rejected(
    client: TestClient,
    db_session: Session,
    id_token: Any,
) -> None:
    response = _sign_in(client, id_token(email_verified=False))

    assert response.status_code == 401
    assert db_session.scalar(select(func.count()).select_from(User)) == 0


def test_expired_token_is_rejected(client: TestClient, id_token: Any) -> None:
    stale = datetime.now(UTC) - timedelta(hours=1)
    response = _sign_in(client, id_token(iat=stale, exp=stale + timedelta(minutes=5)))

    assert response.status_code == 401


def test_token_from_an_unexpected_issuer_is_rejected(client: TestClient, id_token: Any) -> None:
    response = _sign_in(client, id_token(iss="https://evil.example"))

    assert response.status_code == 401


def test_disabled_account_cannot_sign_in(
    client: TestClient,
    db_session: Session,
    id_token: Any,
) -> None:
    user = create_user(db_session, email="ali@example.com", password="hunter2hunter2")
    user.status = "disabled"
    db_session.commit()

    response = _sign_in(client, id_token())

    assert response.status_code == 401


def test_unconfigured_provider_is_unavailable_not_unauthorized(
    client: TestClient,
    oauth_settings: Settings,
    id_token: Any,
) -> None:
    # Apple has no client id in these settings; a missing configuration is ours
    # to fix, so it must not look like the caller's token was bad.
    response = client.post(
        OAUTH_URL,
        json={"provider": "apple", "id_token": id_token()},
    )

    assert response.status_code == 503


def test_password_login_still_requires_a_password_account(
    client: TestClient,
    db_session: Session,
    id_token: Any,
) -> None:
    """A provider account must not become loginable by guessing a password."""

    _sign_in(client, id_token())

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ali@example.com", "password": "whatever-they-guess"},
    )

    assert response.status_code == 401


def test_organization_account_names_its_organization(
    client: TestClient,
    db_session: Session,
    id_token: Any,
) -> None:
    response = _sign_in(
        client,
        id_token(),
        account_type="organization",
        organization_name="Kaira",
    )

    assert response.status_code == 200
    user = db_session.get(User, uuid.UUID(response.json()["user"]["id"]))
    assert user is not None
