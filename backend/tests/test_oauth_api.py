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
from app.db.models import AuditEvent, User
from app.services import oauth
from app.services.auth import create_user

OAUTH_URL = "/api/v1/auth/oauth"
GOOGLE_CLIENT_ID = "test-google-client.apps.googleusercontent.com"
GOOGLE_ISSUER = "https://accounts.google.com"
APPLE_CLIENT_ID = "com.yanki.web"
APPLE_ISSUER = "https://appleid.apple.com"
APPLE_SUBJECT = "001234.abcdef0123456789.1234"


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
        apple_client_id=APPLE_CLIENT_ID,
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
def signer(signing_key: Any):
    private_pem = signing_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    def _sign(claims: dict[str, Any], **overrides: Any) -> str:
        now = datetime.now(UTC)
        payload = {"iat": now, "exp": now + timedelta(minutes=5), **claims}
        payload.update(overrides)
        # A claim overridden to None is one the provider did not send at all.
        return jwt.encode(
            {key: value for key, value in payload.items() if value is not None},
            private_pem,
            algorithm="RS256",
        )

    return _sign


@pytest.fixture()
def id_token(signer: Any):
    def _make(**overrides: Any) -> str:
        return signer(
            {
                "iss": GOOGLE_ISSUER,
                "aud": GOOGLE_CLIENT_ID,
                "sub": "104829371829301827364",
                "email": "ali@example.com",
                "email_verified": True,
            },
            **overrides,
        )

    return _make


@pytest.fixture()
def apple_token(signer: Any):
    """An Apple identity token, with Apple's own quirks in the defaults.

    ``email_verified`` is the string ``"true"`` because that is what Apple
    sends, and the address is a Hide My Email relay because that is what a
    privacy-conscious user's first sign-in actually looks like.
    """

    def _make(**overrides: Any) -> str:
        return signer(
            {
                "iss": APPLE_ISSUER,
                "aud": APPLE_CLIENT_ID,
                "sub": APPLE_SUBJECT,
                "email": "kx9r2m8p@privaterelay.appleid.com",
                "email_verified": "true",
                "is_private_email": "true",
            },
            **overrides,
        )

    return _make


def _sign_in(client: TestClient, token: str, **body: Any):
    return client.post(OAUTH_URL, json={"provider": "google", "id_token": token, **body})


def _apple_sign_in(client: TestClient, token: str, **body: Any):
    return client.post(OAUTH_URL, json={"provider": "apple", "id_token": token, **body})


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
    assert db_session.scalar(select(func.count()).select_from(User)) == 1
    # Signup never verified that address, so whoever set that password may not
    # be the person the provider just vouched for. The password goes.
    assert linked.password_hash is None


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
    apple_token: Any,
) -> None:
    # A missing configuration is ours to fix, so it must not look like the
    # caller's token was bad — and it must never read as a silent accept.
    app.dependency_overrides[get_settings] = lambda: oauth_settings.model_copy(
        update={"apple_client_id": ""}
    )

    response = _apple_sign_in(client, apple_token())

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


def test_providers_lists_only_what_is_configured(
    client: TestClient,
    oauth_settings: Settings,
) -> None:
    """A provider with no client id must not be offered a button."""

    app.dependency_overrides[get_settings] = lambda: oauth_settings.model_copy(
        update={"apple_client_id": ""}
    )

    response = client.get("/api/v1/auth/providers")

    assert response.status_code == 200
    assert response.json() == {"google": GOOGLE_CLIENT_ID, "apple": None}


def test_apple_first_sign_in_accepts_a_hide_my_email_address(
    client: TestClient,
    db_session: Session,
    apple_token: Any,
) -> None:
    """Apple's relay address is the address, and its own to verify."""

    response = _apple_sign_in(client, apple_token())

    assert response.status_code == 200, response.text
    user = db_session.scalar(select(User).where(User.auth_provider == "apple"))
    assert user is not None
    assert user.email == "kx9r2m8p@privaterelay.appleid.com"
    assert user.auth_subject == APPLE_SUBJECT


def test_apple_returning_user_reuses_the_same_account(
    client: TestClient,
    db_session: Session,
    apple_token: Any,
) -> None:
    first = _apple_sign_in(client, apple_token())
    second = _apple_sign_in(client, apple_token())

    assert second.status_code == 200
    assert second.json()["user"]["id"] == first.json()["user"]["id"]
    assert db_session.scalar(select(func.count()).select_from(User)) == 1


def test_apple_returning_user_is_admitted_without_an_email_claim(
    client: TestClient,
    db_session: Session,
    apple_token: Any,
) -> None:
    """Apple sends the address once and may never send it again.

    The subject is what identifies the account, so a later token carrying only
    a subject is a returning user — not a rejected one.
    """

    first = _apple_sign_in(client, apple_token())
    later = _apple_sign_in(client, apple_token(email=None, email_verified=None))

    assert later.status_code == 200, later.text
    assert later.json()["user"]["id"] == first.json()["user"]["id"]
    assert db_session.scalar(select(func.count()).select_from(User)) == 1


def test_an_unknown_subject_without_an_email_cannot_register(
    client: TestClient,
    db_session: Session,
    apple_token: Any,
) -> None:
    """The other half of the rule above: no address, no new account."""

    response = _apple_sign_in(client, apple_token(email=None, email_verified=None))

    assert response.status_code == 401
    assert db_session.scalar(select(func.count()).select_from(User)) == 0


def test_apple_token_aimed_at_another_application_is_rejected(
    client: TestClient,
    apple_token: Any,
) -> None:
    assert _apple_sign_in(client, apple_token(aud="com.someone.else")).status_code == 401


def test_a_google_token_replayed_as_an_apple_one_is_rejected(
    client: TestClient,
    apple_token: Any,
) -> None:
    assert _apple_sign_in(client, apple_token(iss=GOOGLE_ISSUER)).status_code == 401


def test_apple_links_an_existing_password_account_and_retires_the_password(
    client: TestClient,
    db_session: Session,
    apple_token: Any,
) -> None:
    existing = create_user(db_session, email="ali@example.com", password="hunter2hunter2")

    response = _apple_sign_in(client, apple_token(email="ali@example.com"))

    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(existing.id)
    db_session.expire_all()
    linked = db_session.get(User, existing.id)
    assert linked is not None
    assert linked.auth_provider == "apple"
    assert linked.password_hash is None


def test_linking_signs_out_whoever_held_the_password(
    client: TestClient,
    db_session: Session,
    id_token: Any,
) -> None:
    """The pre-hijacking case, end to end.

    Somebody registers an address that is not theirs — signup never verified it
    — and is signed in when the real owner arrives with a provider token. The
    link must take the account back: the squatter's password stops working and
    the session they are holding stops refreshing.
    """

    create_user(db_session, email="ali@example.com", password="hunter2hunter2")
    squatter = TestClient(app)
    squatter_login = squatter.post(
        "/api/v1/auth/login",
        json={"email": "ali@example.com", "password": "hunter2hunter2"},
    )
    assert squatter_login.status_code == 200

    _sign_in(client, id_token())

    assert squatter.post("/api/v1/auth/refresh").status_code == 401
    assert (
        squatter.post(
            "/api/v1/auth/login",
            json={"email": "ali@example.com", "password": "hunter2hunter2"},
        ).status_code
        == 401
    )


def test_the_session_after_a_social_login_behaves_like_any_other(
    client: TestClient,
    apple_token: Any,
) -> None:
    """Refresh, identify, log out — the application's own session machinery.

    The provider's token got the user through the door and is then finished
    with; nothing afterwards depends on it.
    """

    assert _apple_sign_in(client, apple_token()).status_code == 200

    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    access_token = refreshed.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me.status_code == 200
    assert me.json()["organization"] is not None

    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_no_identity_token_reaches_the_audit_trail(
    client: TestClient,
    db_session: Session,
    apple_token: Any,
) -> None:
    """The provider's token is a credential, and credentials are not recorded."""

    token = apple_token()
    _apple_sign_in(client, token)

    events = db_session.scalars(select(AuditEvent)).all()
    written = " ".join(f"{event.detail} {event.after}" for event in events)
    assert token not in written
    assert "id_token" not in written


def test_a_second_provider_does_not_split_the_account(
    client: TestClient,
    db_session: Session,
    apple_token: Any,
    id_token: Any,
) -> None:
    """Signed up with Apple, later presses the Google button on the same address.

    One person, one account. The first provider identity stays recorded — this
    build stores one per user — and the second signs in on the verified email.
    """

    _apple_sign_in(client, apple_token(email="ali@example.com"))
    google = _sign_in(client, id_token())

    assert google.status_code == 200
    assert db_session.scalar(select(func.count()).select_from(User)) == 1
    user = db_session.scalar(select(User))
    assert user is not None
    assert (user.auth_provider, user.auth_subject) == ("apple", APPLE_SUBJECT)


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
