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
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import GoogleOAuthState, Organization, SeoProject, User, Workspace
from app.gsc.base import GoogleProperty
from app.gsc.mock import MockGoogleOAuthProvider
from app.services.search_console import (
    DEFAULT_LOOKBACK_DAYS,
    FINALIZED_DATA_LAG_DAYS,
    MAX_RANGE_DAYS,
    InvalidDateRange,
    OAuthStateExpired,
    OAuthStateInvalid,
    canonical_scopes,
    clamp_row_limit,
    code_challenge_for,
    consume_oauth_state,
    default_date_range,
    hash_oauth_value,
    offer_properties,
    purge_expired_states,
    start_authorization,
    usable_properties,
    validate_date_range,
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


# --------------------------------------------------------------------------
# Date windows
# --------------------------------------------------------------------------


def test_the_default_window_is_28_days_ending_behind_the_lag():
    """Deterministic because `today` is injected rather than read from a clock."""

    start, end = default_date_range(today=date(2026, 8, 6))

    assert end == date(2026, 8, 3)
    assert start == date(2026, 7, 7)
    assert (end - start).days == DEFAULT_LOOKBACK_DAYS - 1


def test_the_default_window_never_reaches_the_days_google_is_still_revising():
    """Ending at 'yesterday' would show numbers that change on reload."""

    today = date(2026, 8, 6)
    _, end = default_date_range(today=today)

    assert (today - end).days == FINALIZED_DATA_LAG_DAYS


def test_an_omitted_bound_falls_back_to_the_default_window():
    today = date(2026, 8, 6)
    default_start, default_end = default_date_range(today=today)

    start, end = validate_date_range(None, None, today=today)
    assert (start, end) == (default_start, default_end)

    start, end = validate_date_range(date(2026, 7, 1), None, today=today)
    assert start == date(2026, 7, 1)
    assert end == default_end


def test_a_backwards_window_is_refused():
    with pytest.raises(InvalidDateRange):
        validate_date_range(date(2026, 8, 1), date(2026, 7, 1), today=date(2026, 8, 6))


def test_a_future_end_is_refused_rather_than_clamped():
    """Silently narrowing the window makes two reports incomparable."""

    with pytest.raises(InvalidDateRange):
        validate_date_range(date(2026, 8, 1), date(2026, 9, 1), today=date(2026, 8, 6))


def test_an_absurdly_wide_window_is_refused():
    today = date(2026, 8, 6)

    with pytest.raises(InvalidDateRange):
        validate_date_range(today - timedelta(days=MAX_RANGE_DAYS), today, today=today)


def test_the_widest_allowed_window_is_accepted():
    today = date(2026, 8, 6)
    start = today - timedelta(days=MAX_RANGE_DAYS - 1)

    assert validate_date_range(start, today, today=today) == (start, today)


def test_a_single_day_window_is_valid():
    today = date(2026, 8, 6)

    assert validate_date_range(today, today, today=today) == (today, today)


# --------------------------------------------------------------------------
# Row limits
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("requested", "expected"),
    [(None, 25), (1, 1), (50, 50), (100, 100), (0, 1), (-5, 1), (1000, 100)],
)
def test_the_row_limit_is_clamped_into_range(requested, expected):
    """Bounded here as well as in the schema, for callers that skip the schema."""

    assert clamp_row_limit(requested) == expected


# --------------------------------------------------------------------------
# Offering properties
# --------------------------------------------------------------------------


def _property(site_url: str, permission_level: str = "siteOwner") -> GoogleProperty:
    return GoogleProperty(site_url=site_url, permission_level=permission_level)


def test_unverified_properties_are_dropped_and_unknown_levels_are_kept():
    """Google adds permission levels; hiding one for being unfamiliar is worse.

    ``ftp://`` is the unparseable case rather than a bare word: the project
    normalizer accepts single-label hosts on purpose (``localhost``), so
    "nonsense" is a valid host to it and dropping it here would be this module
    disagreeing with the one it deliberately shares.
    """

    kept = usable_properties(
        (
            _property("https://a.test/", "siteUnverifiedUser"),
            _property("https://b.test/", "siteRestrictedUser"),
            _property("https://c.test/", "siteOwner"),
            _property("ftp://d.test/", "siteOwner"),
        )
    )

    assert [item.site_url for item in kept] == ["https://b.test/", "https://c.test/"]


def test_offered_properties_put_the_match_first_then_the_selection():
    offered = offer_properties(
        (
            _property("https://zzz.test/"),
            _property("https://aaa.test/"),
            _property("sc-domain:example.com"),
        ),
        project_domain_key="example.com",
        selected_site_url="https://zzz.test/",
    )

    assert [item.site_url for item in offered] == [
        "sc-domain:example.com",
        "https://zzz.test/",
        "https://aaa.test/",
    ]
    assert offered[0].matches_project_domain is True
    assert offered[1].currently_selected is True


def test_the_offer_ordering_is_total_so_it_cannot_shuffle():
    """Same input, same order — a list that reorders makes a user doubt it."""

    properties = (
        _property("https://b.test/"),
        _property("https://a.test/"),
        _property("https://c.test/"),
    )

    first = offer_properties(properties, project_domain_key="x.test", selected_site_url=None)
    second = offer_properties(properties, project_domain_key="x.test", selected_site_url=None)

    assert [i.site_url for i in first] == [i.site_url for i in second]
    assert [i.site_url for i in first] == [
        "https://a.test/",
        "https://b.test/",
        "https://c.test/",
    ]


def test_nothing_is_ever_marked_selected_by_matching_alone():
    """Suggesting is not choosing. Only a stored link sets currently_selected."""

    offered = offer_properties(
        (_property("sc-domain:example.com"),),
        project_domain_key="example.com",
        selected_site_url=None,
    )

    assert offered[0].matches_project_domain is True
    assert offered[0].currently_selected is False
