"""HTTP routes for email/password authentication."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth_cookies import clear_refresh_cookie, set_refresh_cookie
from app.api.auth_dependencies import get_current_user
from app.api.schemas import LoginRequest, LoginResponse, RefreshResponse, SignupRequest, UserOut
from app.config import Settings, get_settings
from app.db.models import User
from app.db.session import get_session
from app.services.auth import authenticate_user, create_user, get_user_by_email
from app.services.auth_sessions import (
    InvalidRefreshSessionError,
    RefreshTokenReuseDetectedError,
    revoke_refresh_session_family,
    rotate_refresh_session,
    start_refresh_session,
)
from app.services.tokens import TokenConfigurationError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/signup",
    status_code=status.HTTP_201_CREATED,
    response_model=UserOut,
)
def signup(
    payload: SignupRequest,
    session: Session = Depends(get_session),
) -> UserOut:
    """Create a user account with a hashed password."""

    if get_user_by_email(session, payload.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="email already registered",
        )

    try:
        user = create_user(
            session,
            email=payload.email,
            password=payload.password,
        )
    except IntegrityError as exc:
        # Handles the race where two requests try to register the same email
        # between the lookup above and the database insert.
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="email already registered",
        ) from exc

    return UserOut.model_validate(user)


@router.post(
    "/login",
    response_model=LoginResponse,
)
def login(
    payload: LoginRequest,
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    """Validate a user's email and password."""

    user = authenticate_user(
        session,
        email=payload.email,
        password=payload.password,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid email or password",
        )

    try:
        tokens = start_refresh_session(
            session,
            user_id=user.id,
            settings=settings,
        )
    except TokenConfigurationError as exc:
        raise _authentication_unavailable() from exc

    set_refresh_cookie(
        response,
        token=tokens.refresh_token,
        settings=settings,
    )

    return LoginResponse(
        user=UserOut.model_validate(user),
        access_token=tokens.access_token.value,
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
)
def refresh(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RefreshResponse | JSONResponse:
    """Rotate the refresh token and return a new access token."""

    refresh_token = request.cookies.get(
        settings.auth_refresh_cookie_name,
    )

    if refresh_token is None:
        return _invalid_refresh_response(settings)

    try:
        tokens = rotate_refresh_session(
            session,
            refresh_token=refresh_token,
            settings=settings,
        )
    except (
        InvalidRefreshSessionError,
        RefreshTokenReuseDetectedError,
    ):
        return _invalid_refresh_response(settings)
    except TokenConfigurationError as exc:
        raise _authentication_unavailable() from exc

    set_refresh_cookie(
        response,
        token=tokens.refresh_token,
        settings=settings,
    )

    return RefreshResponse(
        access_token=tokens.access_token.value,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
def logout(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Revoke the current refresh-token family and clear its cookie."""

    refresh_token = request.cookies.get(
        settings.auth_refresh_cookie_name,
    )

    if refresh_token is not None:
        try:
            revoke_refresh_session_family(
                session,
                refresh_token=refresh_token,
                settings=settings,
            )
        except TokenConfigurationError:
            unavailable_response = JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "detail": "authentication unavailable",
                },
            )
            clear_refresh_cookie(
                unavailable_response,
                settings=settings,
            )
            return unavailable_response

    logout_response = Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )
    clear_refresh_cookie(
        logout_response,
        settings=settings,
    )

    return logout_response


@router.get(
    "/me",
    response_model=UserOut,
)
def me(
    current_user: User = Depends(get_current_user),
) -> UserOut:
    """Return the user represented by the access bearer token."""

    return UserOut.model_validate(current_user)


def _invalid_refresh_response(
    settings: Settings,
) -> JSONResponse:
    response = JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={
            "detail": "invalid or missing refresh token",
        },
    )
    clear_refresh_cookie(
        response,
        settings=settings,
    )

    return response


def _authentication_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="authentication unavailable",
    )
