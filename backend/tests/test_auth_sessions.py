"""Tests for refresh-session persistence, rotation, and revocation."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import AuthSession, User
from app.services.auth_sessions import (
    InvalidRefreshSessionError,
    RefreshTokenReuseDetectedError,
    revoke_refresh_session_family,
    rotate_refresh_session,
    start_refresh_session,
)
from app.services.tokens import (
    TokenType,
    calculate_refresh_family_expiry,
    decode_token,
    hash_refresh_jti,
    issue_refresh_token,
)


@pytest.fixture
def token_settings() -> Settings:
    return Settings(
        jwt_secret_key=SecretStr("a" * 64),
        jwt_issuer="test-yanki-api",
        jwt_audience="test-yanki-web",
        jwt_access_token_minutes=15,
        jwt_refresh_token_days=30,
        jwt_clock_skew_seconds=0,
    )


def test_start_refresh_session_persists_token_family(
    db_session: Session,
    token_settings: Settings,
) -> None:
    user = _create_user(db_session)
    now = datetime.now(UTC).replace(microsecond=0)

    tokens = start_refresh_session(
        db_session,
        user_id=user.id,
        settings=token_settings,
        now=now,
    )

    auth_session = db_session.scalar(select(AuthSession))

    assert auth_session is not None
    assert auth_session.user_id == user.id
    assert auth_session.family_id == tokens.family_id
    assert auth_session.consumed_at is None
    assert auth_session.revoked_at is None
    assert auth_session.replaced_by_id is None

    access_claims = decode_token(
        tokens.access_token.value,
        expected_type=TokenType.ACCESS,
        settings=token_settings,
    )
    refresh_claims = decode_token(
        tokens.refresh_token.value,
        expected_type=TokenType.REFRESH,
        settings=token_settings,
    )

    assert access_claims.user_id == user.id
    assert refresh_claims.user_id == user.id
    assert refresh_claims.expires_at == tokens.refresh_token.expires_at


def test_rotate_refresh_session_consumes_old_token_and_creates_successor(
    db_session: Session,
    token_settings: Settings,
) -> None:
    user = _create_user(db_session)
    started = start_refresh_session(
        db_session,
        user_id=user.id,
        settings=token_settings,
    )

    rotated = rotate_refresh_session(
        db_session,
        refresh_token=started.refresh_token.value,
        settings=token_settings,
    )

    db_session.expire_all()

    family_rows = list(
        db_session.scalars(
            select(AuthSession).where(
                AuthSession.family_id == started.family_id,
            ),
        ),
    )

    assert len(family_rows) == 2
    assert rotated.family_id == started.family_id

    original = next(
        row
        for row in family_rows
        if row.refresh_jti_hash != _refresh_jti_hash(rotated, token_settings)
    )
    successor = next(
        row
        for row in family_rows
        if row.refresh_jti_hash == _refresh_jti_hash(rotated, token_settings)
    )

    assert original.consumed_at is not None
    assert original.replaced_by_id == successor.id
    assert successor.consumed_at is None
    assert successor.replaced_by_id is None
    assert successor.revoked_at is None
    assert _as_utc(original.expires_at) == _as_utc(successor.expires_at)
    assert rotated.refresh_token.expires_at == _as_utc(successor.expires_at)


def test_reusing_consumed_refresh_token_revokes_whole_family(
    db_session: Session,
    token_settings: Settings,
) -> None:
    user = _create_user(db_session)
    started = start_refresh_session(
        db_session,
        user_id=user.id,
        settings=token_settings,
    )
    rotated = rotate_refresh_session(
        db_session,
        refresh_token=started.refresh_token.value,
        settings=token_settings,
    )

    with pytest.raises(
        RefreshTokenReuseDetectedError,
        match="reuse detected",
    ):
        rotate_refresh_session(
            db_session,
            refresh_token=started.refresh_token.value,
            settings=token_settings,
        )

    db_session.expire_all()

    family_rows = list(
        db_session.scalars(
            select(AuthSession).where(
                AuthSession.family_id == started.family_id,
            ),
        ),
    )

    assert len(family_rows) == 2
    assert all(row.revoked_at is not None for row in family_rows)

    with pytest.raises(
        InvalidRefreshSessionError,
        match="revoked",
    ):
        rotate_refresh_session(
            db_session,
            refresh_token=rotated.refresh_token.value,
            settings=token_settings,
        )


def test_logout_revokes_only_matching_session_family(
    db_session: Session,
    token_settings: Settings,
) -> None:
    user = _create_user(db_session)

    first_session = start_refresh_session(
        db_session,
        user_id=user.id,
        settings=token_settings,
    )
    second_session = start_refresh_session(
        db_session,
        user_id=user.id,
        settings=token_settings,
    )

    revoked = revoke_refresh_session_family(
        db_session,
        refresh_token=first_session.refresh_token.value,
        settings=token_settings,
    )

    assert revoked is True

    db_session.expire_all()

    first_family = list(
        db_session.scalars(
            select(AuthSession).where(
                AuthSession.family_id == first_session.family_id,
            ),
        ),
    )
    second_family = list(
        db_session.scalars(
            select(AuthSession).where(
                AuthSession.family_id == second_session.family_id,
            ),
        ),
    )

    assert all(row.revoked_at is not None for row in first_family)
    assert all(row.revoked_at is None for row in second_family)


def test_valid_but_unknown_refresh_token_is_rejected(
    db_session: Session,
    token_settings: Settings,
) -> None:
    user = _create_user(db_session)
    now = datetime.now(UTC).replace(microsecond=0)
    family_expiry = calculate_refresh_family_expiry(
        settings=token_settings,
        now=now,
    )
    unknown_token = issue_refresh_token(
        user.id,
        expires_at=family_expiry,
        settings=token_settings,
        now=now,
    )

    with pytest.raises(
        InvalidRefreshSessionError,
        match="invalid refresh session",
    ):
        rotate_refresh_session(
            db_session,
            refresh_token=unknown_token.value,
            settings=token_settings,
        )


def _create_user(
    db_session: Session,
    *,
    email: str | None = None,
) -> User:
    user = User(
        email=email or f"{uuid.uuid4()}@example.com",
        password_hash="test-password-hash",
    )
    db_session.add(user)
    db_session.commit()

    return user


def _refresh_jti_hash(
    tokens,
    settings: Settings,
) -> str:
    return hash_refresh_jti(
        tokens.refresh_token.jti,
        settings=settings,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)
