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


def get_optional_user(
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
) -> User | None:
    """The signed-in user, or ``None`` — for routes open to both.

    The invitation-accept endpoint is the reason this exists: the same link has
    to work for a stranger who needs an account created and for a member of
    another organization who is already signed in. Refusing anonymous callers
    would break the first, and ignoring the bearer would make the second create
    a duplicate account.

    A *malformed or expired* token returns ``None`` rather than raising. On a
    route that anonymous callers may use, a stale token in a tab is not an
    error to surface — it is a caller who is simply not signed in.
    """

    if credentials is None or credentials.scheme.lower() != "bearer":
        return None

    try:
        claims = decode_token(
            credentials.credentials,
            expected_type=TokenType.ACCESS,
            settings=settings,
        )
    except (TokenValidationError, TokenConfigurationError):
        return None

    return session.get(User, claims.user_id)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or missing access token",
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )
