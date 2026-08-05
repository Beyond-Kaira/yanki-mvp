"""HTTP routes for email/password authentication."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth_cookies import clear_refresh_cookie, set_refresh_cookie
from app.api.auth_dependencies import get_current_user
from app.api.schemas import (
    CurrentUserOut,
    LoginRequest,
    LoginResponse,
    OrganizationOut,
    RefreshResponse,
    SignupRequest,
    UserOut,
)
from app.config import Settings, get_settings
from app.db.models import Organization, User
from app.db.session import get_session
from app.services import audit
from app.services.auth import (
    audit_context,
    authenticate_user,
    create_user,
    get_user_by_email,
)
from app.services.auth_sessions import (
    InvalidRefreshSessionError,
    RefreshTokenReuseDetectedError,
    revoke_refresh_session_family,
    rotate_refresh_session,
    start_refresh_session,
)
from app.services.permissions import permissions_for
from app.services.tenancy import OrgScopeRequired, resolve_org_context
from app.services.tokens import (
    TokenConfigurationError,
    TokenType,
    TokenValidationError,
    decode_token,
)

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
            account_type=payload.account_type,
            organization_name=payload.organization_name,
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
            # Read the user BEFORE revoking: afterwards the token is spent and
            # there is nothing left to attribute the event to. A logout that
            # cannot be attributed is the one event in the session lifecycle
            # that would be missing from the trail — "when did they leave?" is
            # half of "were they here when this happened?".
            revoked_user = _user_from_refresh_token(session, refresh_token, settings)

            revoked = revoke_refresh_session_family(
                session,
                refresh_token=refresh_token,
                settings=settings,
            )
            if revoked and revoked_user is not None:
                audit.emit(
                    session,
                    action="auth:logout",
                    context=audit_context(session, revoked_user),
                    actor_type="user",
                    actor_id=revoked_user.id,
                    actor_label=revoked_user.email,
                    entity_type="user",
                    entity_id=revoked_user.id,
                )
                session.commit()
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
    response_model=CurrentUserOut,
)
def me(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> CurrentUserOut:
    """Who you are, which organization you are acting in, and what you may do.

    The role and permission list ride along so the UI can hide a control the
    caller cannot use, instead of showing it and failing on click. They are for
    RENDERING ONLY — every endpoint enforces its own permission independently,
    so a client that lies about this list gets a 403 exactly as before.
    """

    organization = None
    role = None
    permissions: list[str] = []
    try:
        context = resolve_org_context(session, user=current_user)
    except OrgScopeRequired:
        # A user with no organization can still see who they are. Failing the
        # whole call would make an edge case look like a broken session.
        context = None
    if context is not None and context.org_id is not None:
        org = session.get(Organization, context.org_id)
        if org is not None:
            organization = OrganizationOut.model_validate(org)
        role = context.role
        permissions = sorted(permissions_for(context.role))

    return CurrentUserOut(
        id=current_user.id,
        email=current_user.email,
        created_at=current_user.created_at,
        status=current_user.status,
        organization=organization,
        role=role,
        permissions=permissions,
    )


def _user_from_refresh_token(
    session: Session,
    refresh_token: str,
    settings: Settings,
) -> User | None:
    """Who a refresh token belongs to, or ``None`` for anything unusable.

    Deliberately silent about *why* it returns None. Logout must stay an
    idempotent no-op that never discloses whether the supplied token was ever
    valid — the same posture ``revoke_refresh_session_family`` takes — so a
    malformed, unknown or expired token simply produces no audit event rather
    than an event saying "somebody tried to log out with a bad token", which
    would be a way to probe token validity through the log.
    """

    try:
        claims = decode_token(
            refresh_token,
            expected_type=TokenType.REFRESH,
            settings=settings,
        )
    except TokenValidationError:
        return None
    return session.get(User, claims.user_id)


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
