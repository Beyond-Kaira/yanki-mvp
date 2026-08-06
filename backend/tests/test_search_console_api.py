"""The Google OAuth connect flow over real HTTP (P9.2).

Four properties only the boundary can get wrong, each with a plausible
implementation that fails it:

**Darkness.** ``GSC_ENABLED=0`` must make both halves indistinguishable from a
feature that does not exist — a 403 has already confirmed it does.

**Who may connect.** Authorizing Yanki against somebody's Google estate is a
standing third-party grant, not a read. A Viewer holding ``project:read`` must
not be able to start one.

**Whose project.** Every call is exercised with a second organization present,
so a missing tenant predicate cannot pass by being invisible.

**Whose identity.** The callback authenticates nobody. Everything it acts on —
the organization, the user, the project — comes from the state row, and the
identity comes from a verified ID token bound to that row by nonce. The tests
that matter most here are the ones that hand it a *valid* token belonging to a
different attempt.

Every test runs against ``MockGoogleOAuthProvider``, injected through
``dependency_overrides``. Nothing reaches Google, and no real key is used.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.auth_dependencies import get_current_user
from app.api.main import app
from app.api.search_console_routes import get_provider
from app.config import GOOGLE_OAUTH_SCOPES, Settings, get_settings
from app.db.models import (
    GoogleConnection,
    GoogleOAuthState,
    Membership,
    Organization,
    SeoProject,
    User,
    Workspace,
)
from app.gsc.mock import MockGoogleOAuthProvider
from app.services.auth import hash_password
from app.services.search_console import hash_oauth_value
from app.services.token_crypto import decrypt_secret, generate_encryption_key

ENCRYPTION_KEY = generate_encryption_key()
FRONTEND_ORIGIN = "http://localhost:8140"
CALLBACK_PATH = "/api/v1/integrations/google-search-console/callback"


def _connect_url(project: SeoProject) -> str:
    return f"/api/v1/seo-projects/{project.id}/search-console/connect"


@pytest.fixture()
def gsc_settings() -> Settings:
    return Settings(
        gsc_enabled=True,
        google_oauth_client_id="test-client.apps.googleusercontent.com",
        google_oauth_client_secret="test-client-secret",
        google_oauth_redirect_uri=f"http://localhost:8141{CALLBACK_PATH}",
        token_encryption_key=ENCRYPTION_KEY,
        public_base_url=FRONTEND_ORIGIN,
    )


@pytest.fixture()
def provider() -> MockGoogleOAuthProvider:
    return MockGoogleOAuthProvider()


@pytest.fixture()
def enabled(gsc_settings, provider) -> Iterator[MockGoogleOAuthProvider]:
    """The module switched on, on the mock Google."""

    app.dependency_overrides[get_settings] = lambda: gsc_settings
    app.dependency_overrides[get_provider] = lambda: provider
    yield provider
    app.dependency_overrides.pop(get_settings, None)
    app.dependency_overrides.pop(get_provider, None)


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_settings, None)
    app.dependency_overrides.pop(get_provider, None)


@pytest.fixture()
def make_org(db_session: Session) -> Callable[..., tuple[User, SeoProject]]:
    """A user, their org, an active membership, and one SEO project."""

    def _make(slug: str = "acme", *, role: str = "analyst") -> tuple[User, SeoProject]:
        user = User(email=f"{slug}@example.test", password_hash=hash_password("correct-horse"))
        db_session.add(user)
        db_session.flush()

        org = Organization(name=slug.title(), slug=slug, kind="personal", owner_user_id=user.id)
        db_session.add(org)
        db_session.flush()

        workspace = Workspace(org_id=org.id, name="Default", slug="default", is_default=True)
        db_session.add(workspace)
        db_session.flush()

        db_session.add(Membership(org_id=org.id, user_id=user.id, role=role, status="active"))

        project = SeoProject(
            user_id=user.id,
            org_id=org.id,
            workspace_id=workspace.id,
            name=f"{slug}.test",
            domain=f"https://{slug}.test/",
            domain_key=f"{slug}.test",
        )
        db_session.add(project)
        db_session.commit()
        return user, project

    return _make


def _sign_in(user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


def _start(client: TestClient, project: SeoProject) -> str:
    """Start a flow and return the raw state from the authorization URL."""

    response = client.post(_connect_url(project))
    assert response.status_code == 201, response.text
    query = parse_qs(urlsplit(response.json()["authorization_url"]).query)
    return query["state"][0]


def _reason(response) -> str | None:
    return parse_qs(urlsplit(response.headers["location"]).query).get("reason", [None])[0]


def _gsc_status(response) -> str:
    return parse_qs(urlsplit(response.headers["location"]).query)["gsc"][0]


def _as_utc(value: datetime) -> datetime:
    """SQLite drops the tzinfo it was handed; Postgres does not. Normalize."""

    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


# --------------------------------------------------------------------------
# Darkness, authentication, authorization, tenancy
# --------------------------------------------------------------------------


def test_connect_is_404_while_the_feature_is_off(client, make_org):
    user, project = make_org()
    _sign_in(user)

    response = client.post(_connect_url(project))

    assert response.status_code == 404


def test_the_callback_is_404_while_the_feature_is_off(client):
    response = client.get(CALLBACK_PATH, params={"state": "anything"})

    assert response.status_code == 404


def test_connect_requires_authentication(client, enabled, make_org):
    _, project = make_org()

    response = client.post(_connect_url(project))

    assert response.status_code in (401, 403)


def test_a_viewer_may_not_connect(client, enabled, make_org, db_session):
    """Reading a project and granting Yanki access to Google are different acts."""

    user, project = make_org(role="viewer")
    _sign_in(user)

    response = client.post(_connect_url(project))

    assert response.status_code == 403
    assert db_session.query(GoogleOAuthState).count() == 0


def test_another_organizations_project_is_404_not_403(client, enabled, make_org):
    _, other_project = make_org("globex")
    intruder, _ = make_org("acme")
    _sign_in(intruder)

    response = client.post(_connect_url(other_project))

    assert response.status_code == 404


# --------------------------------------------------------------------------
# Starting a flow
# --------------------------------------------------------------------------


def test_connect_returns_an_authorization_url_and_records_the_attempt(
    client, enabled, make_org, db_session
):
    user, project = make_org()
    _sign_in(user)

    response = client.post(_connect_url(project))

    assert response.status_code == 201
    query = parse_qs(urlsplit(response.json()["authorization_url"]).query)

    state = db_session.query(GoogleOAuthState).one()
    assert state.org_id == project.org_id
    assert state.user_id == user.id
    assert state.seo_project_id == project.id
    assert state.consumed_at is None
    assert _as_utc(state.expires_at) > datetime.now(UTC)

    # The row holds hashes of what the URL carries, and the verifier.
    assert state.state_hash == hash_oauth_value(query["state"][0])
    assert state.nonce_hash == hash_oauth_value(query["nonce"][0])
    assert state.code_verifier


def test_the_database_never_holds_the_raw_state_or_nonce(client, enabled, make_org, db_session):
    user, project = make_org()
    _sign_in(user)

    response = client.post(_connect_url(project))
    query = parse_qs(urlsplit(response.json()["authorization_url"]).query)
    raw_state, raw_nonce = query["state"][0], query["nonce"][0]

    state = db_session.query(GoogleOAuthState).one()
    assert raw_state not in (state.state_hash, state.nonce_hash, state.code_verifier)
    assert raw_nonce not in (state.state_hash, state.nonce_hash, state.code_verifier)


def test_the_response_carries_nothing_but_the_url(client, enabled, make_org):
    """No verifier, no nonce, no state field, no secret."""

    user, project = make_org()
    _sign_in(user)

    payload = client.post(_connect_url(project)).json()

    assert set(payload) == {"authorization_url"}
    body = client.post(_connect_url(project)).text
    assert "test-client-secret" not in body


def test_the_authorization_url_carries_the_pkce_and_oidc_parameters(client, enabled, make_org):
    user, project = make_org()
    _sign_in(user)

    url = client.post(_connect_url(project)).json()["authorization_url"]
    query = parse_qs(urlsplit(url).query)

    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["access_type"] == ["offline"]
    assert query["include_granted_scopes"] == ["true"]
    assert query["prompt"] == ["consent select_account"]
    assert query["code_challenge"][0]
    assert query["nonce"][0]


def test_the_authorization_url_requests_exactly_the_three_agreed_scopes(client, enabled, make_org):
    user, project = make_org()
    _sign_in(user)

    url = client.post(_connect_url(project)).json()["authorization_url"]
    scopes = parse_qs(urlsplit(url).query)["scope"][0].split()

    assert scopes == list(GOOGLE_OAUTH_SCOPES)
    assert "https://www.googleapis.com/auth/webmasters.readonly" in scopes


def test_the_authorization_url_asks_for_no_analytics_and_no_write_scope(client, enabled, make_org):
    """This slice reads Search Console. It has no business with Analytics."""

    user, project = make_org()
    _sign_in(user)

    url = client.post(_connect_url(project)).json()["authorization_url"]
    scope = parse_qs(urlsplit(url).query)["scope"][0]

    assert "analytics" not in scope
    assert "https://www.googleapis.com/auth/webmasters " not in f"{scope} "


def test_two_attempts_produce_different_states(client, enabled, make_org, db_session):
    user, project = make_org()
    _sign_in(user)

    first = _start(client, project)
    second = _start(client, project)

    assert first != second
    assert db_session.query(GoogleOAuthState).count() == 2


def test_starting_a_flow_sweeps_expired_attempts(client, enabled, make_org, db_session):
    user, project = make_org()
    stale = GoogleOAuthState(
        state_hash="stale",
        nonce_hash="stale-nonce",
        code_verifier="stale-verifier",
        org_id=project.org_id,
        user_id=user.id,
        seo_project_id=project.id,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    db_session.add(stale)
    db_session.commit()

    _sign_in(user)
    _start(client, project)

    remaining = db_session.query(GoogleOAuthState).all()
    assert [row.state_hash for row in remaining] != ["stale"]
    assert len(remaining) == 1


# --------------------------------------------------------------------------
# The callback: the happy path
# --------------------------------------------------------------------------


def test_a_valid_callback_stores_an_encrypted_connection(
    client, enabled, make_org, db_session, gsc_settings
):
    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)

    response = client.get(
        CALLBACK_PATH, params={"code": "auth-code", "state": state}, follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["location"] == (
        f"{FRONTEND_ORIGIN}/site-audit/{project.id}?gsc=connected"
    )

    connection = db_session.query(GoogleConnection).one()
    assert connection.org_id == project.org_id
    assert connection.google_account_id == "mock-google-sub"
    assert connection.google_account_email == "owner@example.test"
    assert connection.status == "active"
    assert connection.connected_by_user_id == user.id
    assert (
        decrypt_secret(connection.refresh_token_ciphertext, settings=gsc_settings)
        == "mock-refresh-token"
    )


def test_the_refresh_token_is_not_stored_in_the_clear(client, enabled, make_org, db_session):
    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)
    client.get(CALLBACK_PATH, params={"code": "c", "state": state}, follow_redirects=False)

    connection = db_session.query(GoogleConnection).one()

    assert b"mock-refresh-token" not in connection.refresh_token_ciphertext


def test_the_access_token_is_never_stored_or_returned(client, enabled, make_org, db_session):
    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)

    response = client.get(
        CALLBACK_PATH, params={"code": "c", "state": state}, follow_redirects=False
    )

    assert "mock-access-token" not in response.text
    assert "mock-access-token" not in response.headers["location"]

    connection = db_session.query(GoogleConnection).one()
    columns = {
        column.name: getattr(connection, column.name) for column in connection.__table__.columns
    }
    assert not any("mock-access-token" == str(value) for value in columns.values())
    assert "access_token" not in columns


def test_the_pkce_verifier_from_the_state_row_reaches_the_exchange(
    client, enabled, make_org, db_session
):
    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)
    stored_verifier = db_session.query(GoogleOAuthState).one().code_verifier

    client.get(CALLBACK_PATH, params={"code": "c", "state": state}, follow_redirects=False)

    assert enabled.exchanges == [{"code": "c", "code_verifier": stored_verifier}]


def test_the_granted_scopes_are_stored_canonically(client, enabled, make_org, db_session):
    """Same grant, same stored value — whatever order Google happens to send."""

    enabled.granted_scope = "https://www.googleapis.com/auth/webmasters.readonly  email   openid"
    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)

    client.get(CALLBACK_PATH, params={"code": "c", "state": state}, follow_redirects=False)

    connection = db_session.query(GoogleConnection).one()
    assert connection.scopes == ("email https://www.googleapis.com/auth/webmasters.readonly openid")


# --------------------------------------------------------------------------
# The callback: state handling
# --------------------------------------------------------------------------


def test_a_replayed_state_is_refused(client, enabled, make_org, db_session):
    """The whole reason consumed_at exists."""

    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)

    first = client.get(CALLBACK_PATH, params={"code": "c", "state": state}, follow_redirects=False)
    second = client.get(CALLBACK_PATH, params={"code": "c", "state": state}, follow_redirects=False)

    assert _gsc_status(first) == "connected"
    assert _reason(second) == "invalid_state"
    assert db_session.query(GoogleConnection).count() == 1


def test_an_expired_state_is_refused(client, enabled, make_org, db_session):
    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)

    row = db_session.query(GoogleOAuthState).one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    response = client.get(
        CALLBACK_PATH, params={"code": "c", "state": state}, follow_redirects=False
    )

    assert _reason(response) == "expired_state"
    assert db_session.query(GoogleConnection).count() == 0


def test_an_unknown_state_is_refused(client, enabled, make_org, db_session):
    user, project = make_org()
    _sign_in(user)
    _start(client, project)

    response = client.get(
        CALLBACK_PATH,
        params={"code": "c", "state": "a-state-nobody-issued"},
        follow_redirects=False,
    )

    assert _reason(response) == "invalid_state"
    assert db_session.query(GoogleConnection).count() == 0


def test_a_missing_state_is_refused(client, enabled):
    response = client.get(CALLBACK_PATH, params={"code": "c"}, follow_redirects=False)

    assert _reason(response) == "invalid_state"


def test_a_declined_consent_redirects_to_the_project(client, enabled, make_org, db_session):
    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)

    response = client.get(
        CALLBACK_PATH,
        params={"state": state, "error": "access_denied"},
        follow_redirects=False,
    )

    assert _reason(response) == "access_denied"
    assert f"/site-audit/{project.id}" in response.headers["location"]
    assert db_session.query(GoogleConnection).count() == 0


def test_a_declined_consent_still_spends_the_state(client, enabled, make_org, db_session):
    """A refused attempt must not leave a replayable state behind."""

    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)

    client.get(
        CALLBACK_PATH,
        params={"state": state, "error": "access_denied"},
        follow_redirects=False,
    )

    assert db_session.query(GoogleOAuthState).one().consumed_at is not None


# --------------------------------------------------------------------------
# The callback: identity
# --------------------------------------------------------------------------


def test_an_id_token_minted_for_another_attempt_is_refused(client, enabled, make_org, db_session):
    """A perfectly valid ID token, bound to a different nonce. The core check."""

    enabled.id_token_nonce = "a-nonce-from-somewhere-else"
    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)

    response = client.get(
        CALLBACK_PATH, params={"code": "c", "state": state}, follow_redirects=False
    )

    assert _reason(response) == "invalid_identity"
    assert db_session.query(GoogleConnection).count() == 0


def test_an_unverifiable_id_token_is_refused(client, enabled, make_org, db_session):
    """Bad signature, wrong audience, wrong issuer, expired — all one outcome."""

    enabled.fail_identity = True
    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)

    response = client.get(
        CALLBACK_PATH, params={"code": "c", "state": state}, follow_redirects=False
    )

    assert _reason(response) == "invalid_identity"
    assert db_session.query(GoogleConnection).count() == 0


def test_an_unverified_email_is_refused(client, enabled, make_org, db_session):
    enabled.email_verified = False
    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)

    response = client.get(
        CALLBACK_PATH, params={"code": "c", "state": state}, follow_redirects=False
    )

    assert _reason(response) == "invalid_identity"
    assert db_session.query(GoogleConnection).count() == 0


@pytest.mark.parametrize("missing", ["subject", "email"])
def test_a_token_without_an_identity_claim_is_refused(
    client, enabled, make_org, db_session, missing
):
    setattr(enabled, missing, "")
    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)

    response = client.get(
        CALLBACK_PATH, params={"code": "c", "state": state}, follow_redirects=False
    )

    assert _reason(response) == "invalid_identity"
    assert db_session.query(GoogleConnection).count() == 0


def test_the_account_is_taken_from_the_token_not_the_query_string(
    client, enabled, make_org, db_session
):
    """Supplying an account in the URL must change nothing."""

    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)

    client.get(
        CALLBACK_PATH,
        params={
            "code": "c",
            "state": state,
            "sub": "attacker-sub",
            "email": "attacker@evil.test",
        },
        follow_redirects=False,
    )

    connection = db_session.query(GoogleConnection).one()
    assert connection.google_account_id == "mock-google-sub"
    assert connection.google_account_email == "owner@example.test"


# --------------------------------------------------------------------------
# The callback: provider failure
# --------------------------------------------------------------------------


def test_a_failed_exchange_redirects_without_leaking_the_reason(
    client, enabled, make_org, db_session
):
    enabled.fail_exchange = True
    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)

    response = client.get(
        CALLBACK_PATH, params={"code": "c", "state": state}, follow_redirects=False
    )

    assert _reason(response) == "provider_error"
    assert "mock google refused" not in response.headers["location"]
    assert db_session.query(GoogleConnection).count() == 0


def test_a_missing_code_is_a_provider_error(client, enabled, make_org):
    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)

    response = client.get(CALLBACK_PATH, params={"state": state}, follow_redirects=False)

    assert _reason(response) == "provider_error"


def test_the_providers_error_text_never_reaches_the_redirect(client, enabled, make_org):
    """Google's own error string is attacker-influenced and is never echoed."""

    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)

    response = client.get(
        CALLBACK_PATH,
        params={
            "state": state,
            "error": "access_denied",
            "error_description": "<script>alert(1)</script>",
        },
        follow_redirects=False,
    )

    location = response.headers["location"]
    assert "script" not in location
    assert "error_description" not in location


# --------------------------------------------------------------------------
# The callback: redirect safety
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hostile",
    [
        {"redirect_uri": "https://evil.test"},
        {"next": "https://evil.test"},
        {"return_to": "//evil.test"},
        {"project_id": str(uuid.uuid4())},
    ],
)
def test_the_redirect_target_cannot_be_influenced_by_the_request(
    client, enabled, make_org, hostile
):
    """The destination is built from the state row and settings. Nothing else."""

    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)

    response = client.get(
        CALLBACK_PATH,
        params={"code": "c", "state": state, **hostile},
        follow_redirects=False,
    )

    assert response.headers["location"] == (
        f"{FRONTEND_ORIGIN}/site-audit/{project.id}?gsc=connected"
    )
    assert "evil.test" not in response.headers["location"]


def test_the_redirect_goes_to_the_frontend_origin_not_the_callback_origin(
    client, enabled, make_org, gsc_settings
):
    """PUBLIC_BASE_URL is the web app; the redirect URI is the API. Not the same."""

    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)

    response = client.get(
        CALLBACK_PATH, params={"code": "c", "state": state}, follow_redirects=False
    )

    assert response.headers["location"].startswith(FRONTEND_ORIGIN)
    assert not response.headers["location"].startswith(gsc_settings.google_oauth_redirect_uri)


# --------------------------------------------------------------------------
# Multiple Google accounts, and reconnecting
# --------------------------------------------------------------------------


def test_reconnecting_the_same_account_updates_rather_than_duplicates(
    client, enabled, make_org, db_session, gsc_settings
):
    user, project = make_org()
    _sign_in(user)

    client.get(
        CALLBACK_PATH,
        params={"code": "c", "state": _start(client, project)},
        follow_redirects=False,
    )
    first_id = db_session.query(GoogleConnection).one().id

    enabled.email = "renamed@example.test"
    enabled.refresh_token = "rotated-refresh-token"
    client.get(
        CALLBACK_PATH,
        params={"code": "c", "state": _start(client, project)},
        follow_redirects=False,
    )

    connection = db_session.query(GoogleConnection).one()
    assert connection.id == first_id
    assert connection.google_account_email == "renamed@example.test"
    assert (
        decrypt_secret(connection.refresh_token_ciphertext, settings=gsc_settings)
        == "rotated-refresh-token"
    )


def test_a_second_google_account_becomes_a_second_connection(client, enabled, make_org, db_session):
    """The agency case, end to end."""

    user, project = make_org()
    _sign_in(user)

    client.get(
        CALLBACK_PATH,
        params={"code": "c", "state": _start(client, project)},
        follow_redirects=False,
    )

    enabled.subject = "second-google-sub"
    enabled.email = "second@example.test"
    client.get(
        CALLBACK_PATH,
        params={"code": "c", "state": _start(client, project)},
        follow_redirects=False,
    )

    accounts = {row.google_account_id for row in db_session.query(GoogleConnection).all()}
    assert accounts == {"mock-google-sub", "second-google-sub"}


def test_connecting_one_account_never_disturbs_another(
    client, enabled, make_org, db_session, gsc_settings
):
    user, project = make_org()
    _sign_in(user)

    client.get(
        CALLBACK_PATH,
        params={"code": "c", "state": _start(client, project)},
        follow_redirects=False,
    )
    untouched = db_session.query(GoogleConnection).one()
    untouched_ciphertext = untouched.refresh_token_ciphertext
    untouched_id = untouched.id

    enabled.subject = "second-google-sub"
    enabled.email = "second@example.test"
    enabled.refresh_token = "a-different-refresh-token"
    client.get(
        CALLBACK_PATH,
        params={"code": "c", "state": _start(client, project)},
        follow_redirects=False,
    )

    db_session.expire_all()
    first = db_session.get(GoogleConnection, untouched_id)
    assert first is not None
    assert first.refresh_token_ciphertext == untouched_ciphertext
    assert decrypt_secret(first.refresh_token_ciphertext, settings=gsc_settings) == (
        "mock-refresh-token"
    )


def test_a_reconnect_without_a_refresh_token_keeps_the_stored_one(
    client, enabled, make_org, db_session, gsc_settings
):
    """Google omits it when it considers the grant unchanged. Overwriting with
    nothing would turn a working connection into a permanently broken one."""

    user, project = make_org()
    _sign_in(user)

    client.get(
        CALLBACK_PATH,
        params={"code": "c", "state": _start(client, project)},
        follow_redirects=False,
    )
    original = db_session.query(GoogleConnection).one().refresh_token_ciphertext

    enabled.refresh_token = None
    response = client.get(
        CALLBACK_PATH,
        params={"code": "c", "state": _start(client, project)},
        follow_redirects=False,
    )

    assert _gsc_status(response) == "connected"
    db_session.expire_all()
    connection = db_session.query(GoogleConnection).one()
    assert connection.refresh_token_ciphertext == original
    assert (
        decrypt_secret(connection.refresh_token_ciphertext, settings=gsc_settings)
        == "mock-refresh-token"
    )


def test_a_first_connection_without_a_refresh_token_is_refused(
    client, enabled, make_org, db_session
):
    """It would look connected and stop working within the hour."""

    enabled.refresh_token = None
    user, project = make_org()
    _sign_in(user)
    state = _start(client, project)

    response = client.get(
        CALLBACK_PATH, params={"code": "c", "state": state}, follow_redirects=False
    )

    assert _reason(response) == "missing_refresh_token"
    assert db_session.query(GoogleConnection).count() == 0


def test_the_published_contract_exposes_connect_and_hides_the_callback():
    """The generated client should be able to start a flow and nothing else.

    The callback is a URL registered with Google, not an interface the frontend
    calls. Publishing it would put a route that authenticates nobody into the
    typed client, which is an invitation to call it from application code.
    """

    schema = app.openapi()
    paths = schema["paths"]

    assert "/api/v1/seo-projects/{project_id}/search-console/connect" in paths
    assert CALLBACK_PATH not in paths


def test_the_published_contract_carries_no_credential_field():
    """The response is one URL. Anything else here would be a leak by schema."""

    schema = app.openapi()
    properties = schema["components"]["schemas"]["SearchConsoleConnectStartOut"]["properties"]

    assert set(properties) == {"authorization_url"}


def test_the_connection_lands_in_the_organization_the_flow_started_in(
    client, enabled, make_org, db_session
):
    """Identity comes from the state row, so a second tenant sees nothing."""

    user, project = make_org("acme")
    make_org("globex")
    _sign_in(user)

    client.get(
        CALLBACK_PATH,
        params={"code": "c", "state": _start(client, project)},
        follow_redirects=False,
    )

    connection = db_session.query(GoogleConnection).one()
    assert connection.org_id == project.org_id
    assert (
        db_session.scalar(
            sa.select(sa.func.count())
            .select_from(GoogleConnection)
            .where(GoogleConnection.org_id != project.org_id)
        )
        == 0
    )
