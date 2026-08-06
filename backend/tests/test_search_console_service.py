"""The service layer's own logic, below HTTP.

``test_search_console_api.py`` drives these through the router, which is the
right place to prove the flow. This file pins the pieces that are easy to get
subtly wrong and hard to see from the outside: the PKCE derivation, the scope
canonicalization, the sweep, and the claim — especially the claim, whose whole
value is what it does under a race the HTTP tests cannot stage.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import GoogleOAuthState, Organization, SeoProject, User, Workspace
from app.gsc.mock import MockGoogleOAuthProvider
from app.services.search_console import (
    OAuthStateExpired,
    OAuthStateInvalid,
    canonical_scopes,
    code_challenge_for,
    consume_oauth_state,
    hash_oauth_value,
    purge_expired_states,
    start_authorization,
)
from app.services.token_crypto import generate_encryption_key


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        gsc_enabled=True,
        google_oauth_client_id="test-client.apps.googleusercontent.com",
        google_oauth_client_secret="secret",
        google_oauth_redirect_uri="http://localhost:8141/cb",
        token_encryption_key=generate_encryption_key(),
        gsc_oauth_state_ttl_seconds=600,
    )


@pytest.fixture()
def make_project(db_session: Session) -> Callable[..., tuple[User, Organization, SeoProject]]:
    def _make(slug: str = "acme") -> tuple[User, Organization, SeoProject]:
        user = User(email=f"{slug}@example.test", password_hash="x")
        db_session.add(user)
        db_session.flush()
        org = Organization(name=slug, slug=slug, kind="personal", owner_user_id=user.id)
        db_session.add(org)
        db_session.flush()
        workspace = Workspace(org_id=org.id, name="Default", slug="default", is_default=True)
        db_session.add(workspace)
        db_session.flush()
        project = SeoProject(
            user_id=user.id,
            org_id=org.id,
            workspace_id=workspace.id,
            name=slug,
            domain=f"https://{slug}.test/",
            domain_key=f"{slug}.test",
        )
        db_session.add(project)
        db_session.commit()
        return user, org, project

    return _make


# --------------------------------------------------------------------------
# PKCE
# --------------------------------------------------------------------------


def test_the_code_challenge_is_unpadded_base64url_of_the_sha256_verifier():
    """RFC 7636 S256. Padding left on is the classic way this silently fails."""

    verifier = "a-verifier-with-enough-entropy-to-be-realistic"
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )

    challenge = code_challenge_for(verifier)

    assert challenge == expected
    assert "=" not in challenge
    assert "+" not in challenge and "/" not in challenge


def test_the_challenge_is_not_the_verifier():
    assert code_challenge_for("verifier") != "verifier"


# --------------------------------------------------------------------------
# Scope canonicalization
# --------------------------------------------------------------------------


def test_the_same_grant_in_any_order_produces_one_stored_value():
    """Google promises no order, so an unsorted store invents scope 'changes'."""

    first = canonical_scopes("openid email https://www.googleapis.com/auth/webmasters.readonly")
    second = canonical_scopes("https://www.googleapis.com/auth/webmasters.readonly openid email")

    assert first == second
    assert first == "email https://www.googleapis.com/auth/webmasters.readonly openid"


@pytest.mark.parametrize(
    "raw",
    [
        "  openid   email  ",
        "openid email openid",
        "openid\temail",
    ],
)
def test_whitespace_and_repetition_collapse(raw):
    assert canonical_scopes(raw) == "email openid"


def test_an_empty_grant_is_an_empty_string_not_a_crash():
    assert canonical_scopes("") == ""
    assert canonical_scopes("   ") == ""


# --------------------------------------------------------------------------
# Hashing
# --------------------------------------------------------------------------


def test_hashing_is_sha256_hex_and_never_the_input():
    raw = "a-state-value"

    digest = hash_oauth_value(raw)

    assert digest == hashlib.sha256(raw.encode()).hexdigest()
    assert len(digest) == 64
    assert raw not in digest


# --------------------------------------------------------------------------
# Starting and claiming
# --------------------------------------------------------------------------


def test_starting_stores_hashes_and_returns_a_url_carrying_the_raw_values(
    db_session, settings, make_project
):
    user, org, project = make_project()
    provider = MockGoogleOAuthProvider()

    started = start_authorization(
        db_session,
        settings=settings,
        provider=provider,
        org_id=org.id,
        user_id=user.id,
        seo_project_id=project.id,
    )
    db_session.commit()

    from urllib.parse import parse_qs, urlsplit

    query = parse_qs(urlsplit(started.authorization_url).query)
    row = db_session.query(GoogleOAuthState).one()

    assert row.state_hash == hash_oauth_value(query["state"][0])
    assert row.nonce_hash == hash_oauth_value(query["nonce"][0])
    assert query["code_challenge"][0] == code_challenge_for(row.code_verifier)


def test_claiming_a_live_state_returns_its_context_and_marks_it_used(
    db_session, settings, make_project
):
    user, org, project = make_project()
    provider = MockGoogleOAuthProvider()
    started = start_authorization(
        db_session,
        settings=settings,
        provider=provider,
        org_id=org.id,
        user_id=user.id,
        seo_project_id=project.id,
    )
    db_session.commit()

    from urllib.parse import parse_qs, urlsplit

    raw_state = parse_qs(urlsplit(started.authorization_url).query)["state"][0]

    claimed = consume_oauth_state(db_session, raw_state=raw_state)
    db_session.commit()

    assert claimed.org_id == org.id
    assert claimed.user_id == user.id
    assert claimed.seo_project_id == project.id
    assert db_session.query(GoogleOAuthState).one().consumed_at is not None


def test_a_second_claim_of_the_same_state_fails(db_session, settings, make_project):
    """The property the whole design rests on: claim, do not check-then-set."""

    user, org, project = make_project()
    started = start_authorization(
        db_session,
        settings=settings,
        provider=MockGoogleOAuthProvider(),
        org_id=org.id,
        user_id=user.id,
        seo_project_id=project.id,
    )
    db_session.commit()

    from urllib.parse import parse_qs, urlsplit

    raw_state = parse_qs(urlsplit(started.authorization_url).query)["state"][0]

    consume_oauth_state(db_session, raw_state=raw_state)
    db_session.commit()

    with pytest.raises(OAuthStateInvalid):
        consume_oauth_state(db_session, raw_state=raw_state)


def test_an_expired_state_reports_expiry_rather_than_invalidity(db_session, settings, make_project):
    """Different words send a user to different actions, so they are separated."""

    user, org, project = make_project()
    raw_state = "expired-state"
    db_session.add(
        GoogleOAuthState(
            state_hash=hash_oauth_value(raw_state),
            nonce_hash=hash_oauth_value("n"),
            code_verifier="v",
            org_id=org.id,
            user_id=user.id,
            seo_project_id=project.id,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    db_session.commit()

    with pytest.raises(OAuthStateExpired):
        consume_oauth_state(db_session, raw_state=raw_state)


def test_an_unknown_state_is_invalid(db_session):
    with pytest.raises(OAuthStateInvalid):
        consume_oauth_state(db_session, raw_state="never-issued")


def test_a_consumed_and_expired_state_reads_as_invalid(db_session, settings, make_project):
    """Already spent wins over merely old — it is the more precise answer."""

    user, org, project = make_project()
    raw_state = "spent-and-old"
    db_session.add(
        GoogleOAuthState(
            state_hash=hash_oauth_value(raw_state),
            nonce_hash=hash_oauth_value("n"),
            code_verifier="v",
            org_id=org.id,
            user_id=user.id,
            seo_project_id=project.id,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
            consumed_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    db_session.commit()

    with pytest.raises(OAuthStateInvalid):
        consume_oauth_state(db_session, raw_state=raw_state)


# --------------------------------------------------------------------------
# The sweep
# --------------------------------------------------------------------------


def test_the_sweep_removes_expired_attempts_and_leaves_live_ones(
    db_session, settings, make_project
):
    user, org, project = make_project()
    now = datetime.now(UTC)

    for label, expires_at in (
        ("live", now + timedelta(minutes=5)),
        ("stale", now - timedelta(minutes=5)),
    ):
        db_session.add(
            GoogleOAuthState(
                state_hash=label,
                nonce_hash=f"{label}-nonce",
                code_verifier="v",
                org_id=org.id,
                user_id=user.id,
                seo_project_id=project.id,
                expires_at=expires_at,
            )
        )
    db_session.commit()

    removed = purge_expired_states(db_session, now=now)
    db_session.commit()

    assert removed == 1
    assert [row.state_hash for row in db_session.query(GoogleOAuthState).all()] == ["live"]
