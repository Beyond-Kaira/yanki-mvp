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

    # Checked on EVERY request, not only at login. An access token is a
    # self-contained JWT that no service can recall, so without this check an
    # administrator disabling an account would be scheduling its disablement for
    # whenever the token happens to expire — while the person carries on working.
    # Revoking their refresh sessions (which disabling also does) closes the slow
    # half; this closes the fast one, at the cost of one primary-key read that
    # every authenticated request was already performing.
    if user.status != "active":
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

    user = session.get(User, claims.user_id)
    # A disabled account is not "signed in as somebody" — it is nobody. Same
    # rule as `get_current_user`; returning the row here would let a disabled
    # user accept an invitation on the strength of a token issued before they
    # were disabled.
    if user is not None and user.status != "active":
        return None
    return user


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or missing access token",
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )
