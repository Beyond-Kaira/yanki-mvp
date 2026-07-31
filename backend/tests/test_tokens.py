"""Tests for JWT issuance and validation helpers."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.services.tokens import (
    JWT_ALGORITHM,
    TokenConfigurationError,
    TokenType,
    TokenValidationError,
    calculate_refresh_family_expiry,
    decode_token,
    hash_refresh_jti,
    issue_access_token,
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


def test_access_token_contains_valid_required_claims(
    token_settings: Settings,
) -> None:
    user_id = uuid.uuid4()
    now = datetime.now(UTC).replace(microsecond=0)

    issued = issue_access_token(
        user_id,
        settings=token_settings,
        now=now,
    )
    claims = decode_token(
        issued.value,
        expected_type=TokenType.ACCESS,
        settings=token_settings,
    )

    assert claims.user_id == user_id
    assert claims.jti == issued.jti
    assert claims.token_type is TokenType.ACCESS
    assert claims.issued_at == now
    assert claims.not_before == now
    assert claims.expires_at == now + timedelta(minutes=15)


def test_refresh_token_keeps_fixed_family_expiry(
    token_settings: Settings,
) -> None:
    user_id = uuid.uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    family_expiry = calculate_refresh_family_expiry(
        settings=token_settings,
        now=now,
    )

    issued = issue_refresh_token(
        user_id,
        expires_at=family_expiry,
        settings=token_settings,
        now=now,
    )
    claims = decode_token(
        issued.value,
        expected_type=TokenType.REFRESH,
        settings=token_settings,
    )

    assert family_expiry == now + timedelta(days=30)
    assert issued.expires_at == family_expiry
    assert claims.expires_at == family_expiry
    assert claims.token_type is TokenType.REFRESH

    digest = hash_refresh_jti(
        issued.jti,
        settings=token_settings,
    )

    assert len(digest) == 64
    assert digest != str(issued.jti)
    assert digest == hash_refresh_jti(
        issued.jti,
        settings=token_settings,
    )


def test_access_token_cannot_be_used_as_refresh_token(
    token_settings: Settings,
) -> None:
    issued = issue_access_token(
        uuid.uuid4(),
        settings=token_settings,
    )

    with pytest.raises(
        TokenValidationError,
        match="unexpected token type",
    ):
        decode_token(
            issued.value,
            expected_type=TokenType.REFRESH,
            settings=token_settings,
        )


def test_expired_token_is_rejected(
    token_settings: Settings,
) -> None:
    issued = issue_access_token(
        uuid.uuid4(),
        settings=token_settings,
        now=datetime.now(UTC) - timedelta(minutes=20),
    )

    with pytest.raises(
        TokenValidationError,
        match="invalid token",
    ):
        decode_token(
            issued.value,
            expected_type=TokenType.ACCESS,
            settings=token_settings,
        )


def test_token_missing_required_claim_is_rejected(
    token_settings: Settings,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)

    payload = _valid_payload(now)
    del payload["jti"]

    token = jwt.encode(
        payload,
        token_settings.jwt_secret_key.get_secret_value(),
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(
        TokenValidationError,
        match="invalid token",
    ):
        decode_token(
            token,
            expected_type=TokenType.ACCESS,
            settings=token_settings,
        )


def test_token_signed_with_unapproved_algorithm_is_rejected(
    token_settings: Settings,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)

    token = jwt.encode(
        _valid_payload(now),
        token_settings.jwt_secret_key.get_secret_value(),
        algorithm="HS512",
    )

    with pytest.raises(
        TokenValidationError,
        match="invalid token",
    ):
        decode_token(
            token,
            expected_type=TokenType.ACCESS,
            settings=token_settings,
        )


def test_short_signing_key_is_rejected() -> None:
    settings = Settings(
        jwt_secret_key=SecretStr("too-short"),
    )

    with pytest.raises(
        TokenConfigurationError,
        match="at least 32 bytes",
    ):
        issue_access_token(
            uuid.uuid4(),
            settings=settings,
        )


def _valid_payload(now: datetime) -> dict[str, Any]:
    return {
        "sub": str(uuid.uuid4()),
        "jti": str(uuid.uuid4()),
        "type": TokenType.ACCESS.value,
        "iss": "test-yanki-api",
        "aud": "test-yanki-web",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=15),
    }
