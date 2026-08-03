"""HTTP cookie helpers for refresh-token authentication."""

from typing import Literal

from fastapi import Response

from app.config import Settings
from app.services.tokens import IssuedToken

REFRESH_COOKIE_PATH = "/api/v1/auth"
REFRESH_COOKIE_SAMESITE: Literal["lax"] = "lax"


def set_refresh_cookie(
    response: Response,
    *,
    token: IssuedToken,
    settings: Settings,
) -> None:
    """Store a refresh token in a restricted HttpOnly cookie."""

    max_age = max(
        0,
        int((token.expires_at - token.issued_at).total_seconds()),
    )

    response.set_cookie(
        key=settings.auth_refresh_cookie_name,
        value=token.value,
        max_age=max_age,
        expires=token.expires_at,
        path=REFRESH_COOKIE_PATH,
        secure=settings.auth_refresh_cookie_secure,
        httponly=True,
        samesite=REFRESH_COOKIE_SAMESITE,
    )


def clear_refresh_cookie(
    response: Response,
    *,
    settings: Settings,
) -> None:
    """Expire the refresh-token cookie using its original attributes."""

    response.delete_cookie(
        key=settings.auth_refresh_cookie_name,
        path=REFRESH_COOKIE_PATH,
        secure=settings.auth_refresh_cookie_secure,
        httponly=True,
        samesite=REFRESH_COOKIE_SAMESITE,
    )
