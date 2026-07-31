"""FastAPI dependencies for bearer-token authentication."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import User
from app.db.session import get_session
from app.services.tokens import (
    TokenConfigurationError,
    TokenType,
    TokenValidationError,
    decode_token,
)

_bearer_scheme = HTTPBearer(
    auto_error=False,
)


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer_scheme),
    ],
    session: Annotated[
        Session,
        Depends(get_session),
    ],
    settings: Annotated[
        Settings,
        Depends(get_settings),
    ],
) -> User:
    """Return the user represented by a valid access bearer token."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    try:
        claims = decode_token(
            credentials.credentials,
            expected_type=TokenType.ACCESS,
            settings=settings,
        )
    except TokenValidationError as exc:
        raise _unauthorized() from exc
    except TokenConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication unavailable",
        ) from exc

    user = session.get(
        User,
        claims.user_id,
    )

    if user is None:
        raise _unauthorized()

    return user


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or missing access token",
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )
