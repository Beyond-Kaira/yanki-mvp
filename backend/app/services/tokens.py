"""JWT issuance and validation helpers."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt
from jwt.exceptions import InvalidTokenError as PyJWTInvalidTokenError

from app.config import Settings, get_settings

JWT_ALGORITHM = "HS256"

_MIN_SECRET_BYTES = 32
_REQUIRED_CLAIMS = (
    "sub",
    "jti",
    "type",
    "iss",
    "aud",
    "iat",
    "nbf",
    "exp",
)


class TokenType(StrEnum):
    """JWT types issued by the application."""

    ACCESS = "access"
    REFRESH = "refresh"


@dataclass(frozen=True, slots=True)
class IssuedToken:
    """A signed token together with the metadata used to create it."""

    value: str
    jti: uuid.UUID
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Validated claims extracted from an application JWT."""

    user_id: uuid.UUID
    jti: uuid.UUID
    token_type: TokenType
    issued_at: datetime
    not_before: datetime
    expires_at: datetime


class TokenConfigurationError(RuntimeError):
    """Raised when JWT configuration is unsafe or incomplete."""


class TokenValidationError(ValueError):
    """Raised when a JWT cannot be trusted or used for the requested purpose."""


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("token timestamps must be timezone-aware")

    return value.astimezone(UTC).replace(microsecond=0)


def _signing_key(settings: Settings) -> str:
    secret = settings.jwt_secret_key.get_secret_value()

    if len(secret.encode("utf-8")) < _MIN_SECRET_BYTES:
        raise TokenConfigurationError(
            "JWT_SECRET_KEY must contain at least 32 bytes",
        )

    return secret


def _issue_token(
    user_id: uuid.UUID,
    *,
    token_type: TokenType,
    issued_at: datetime,
    expires_at: datetime,
    settings: Settings,
) -> IssuedToken:
    if expires_at <= issued_at:
        raise ValueError("token expiration must be after its issue time")

    jti = uuid.uuid4()

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "jti": str(jti),
        "type": token_type.value,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": expires_at,
    }

    value = jwt.encode(
        payload,
        _signing_key(settings),
        algorithm=JWT_ALGORITHM,
    )

    return IssuedToken(
        value=value,
        jti=jti,
        issued_at=issued_at,
        expires_at=expires_at,
    )


def issue_access_token(
    user_id: uuid.UUID,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> IssuedToken:
    """Issue a short-lived bearer token for protected API endpoints."""

    resolved_settings = settings or get_settings()
    issued_at = _as_utc(now or _utcnow())
    expires_at = issued_at + timedelta(
        minutes=resolved_settings.jwt_access_token_minutes,
    )

    return _issue_token(
        user_id,
        token_type=TokenType.ACCESS,
        issued_at=issued_at,
        expires_at=expires_at,
        settings=resolved_settings,
    )


def calculate_refresh_family_expiry(
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> datetime:
    """Return the fixed maximum expiry of a newly created refresh family."""

    resolved_settings = settings or get_settings()
    issued_at = _as_utc(now or _utcnow())

    return issued_at + timedelta(
        days=resolved_settings.jwt_refresh_token_days,
    )


def issue_refresh_token(
    user_id: uuid.UUID,
    *,
    expires_at: datetime,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> IssuedToken:
    """Issue a refresh token without extending its family's fixed expiry."""

    resolved_settings = settings or get_settings()
    issued_at = _as_utc(now or _utcnow())
    normalized_expiry = _as_utc(expires_at)

    return _issue_token(
        user_id,
        token_type=TokenType.REFRESH,
        issued_at=issued_at,
        expires_at=normalized_expiry,
        settings=resolved_settings,
    )


def decode_token(
    token: str,
    *,
    expected_type: TokenType,
    settings: Settings | None = None,
) -> TokenClaims:
    """Validate a JWT and require the requested application token type."""

    resolved_settings = settings or get_settings()

    try:
        payload = jwt.decode(
            token,
            _signing_key(resolved_settings),
            algorithms=[JWT_ALGORITHM],
            audience=resolved_settings.jwt_audience,
            issuer=resolved_settings.jwt_issuer,
            leeway=resolved_settings.jwt_clock_skew_seconds,
            options={
                "require": list(_REQUIRED_CLAIMS),
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
                "strict_aud": True,
            },
        )
    except PyJWTInvalidTokenError as exc:
        raise TokenValidationError("invalid token") from exc

    return _parse_claims(
        payload,
        expected_type=expected_type,
    )


def hash_refresh_jti(
    jti: uuid.UUID,
    *,
    settings: Settings | None = None,
) -> str:
    """Return a keyed digest suitable for storing a refresh JTI in the database."""

    resolved_settings = settings or get_settings()
    key = _signing_key(resolved_settings).encode("utf-8")

    return hmac.new(
        key,
        b"yanki:refresh-jti:" + jti.bytes,
        hashlib.sha256,
    ).hexdigest()


def _parse_claims(
    payload: dict[str, Any],
    *,
    expected_type: TokenType,
) -> TokenClaims:
    try:
        user_id = uuid.UUID(_string_claim(payload, "sub"))
        jti = uuid.UUID(_string_claim(payload, "jti"))
        token_type = TokenType(_string_claim(payload, "type"))
    except (ValueError, AttributeError) as exc:
        raise TokenValidationError("invalid token claims") from exc

    if token_type is not expected_type:
        raise TokenValidationError("unexpected token type")

    return TokenClaims(
        user_id=user_id,
        jti=jti,
        token_type=token_type,
        issued_at=_numeric_date_claim(payload, "iat"),
        not_before=_numeric_date_claim(payload, "nbf"),
        expires_at=_numeric_date_claim(payload, "exp"),
    )


def _string_claim(
    payload: dict[str, Any],
    name: str,
) -> str:
    value = payload.get(name)

    if not isinstance(value, str) or not value:
        raise TokenValidationError(f"invalid {name} claim")

    return value


def _numeric_date_claim(
    payload: dict[str, Any],
    name: str,
) -> datetime:
    value = payload.get(name)

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TokenValidationError(f"invalid {name} claim")

    try:
        return datetime.fromtimestamp(value, UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise TokenValidationError(f"invalid {name} claim") from exc
