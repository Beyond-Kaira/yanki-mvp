"""HTTP routes for email/password authentication."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth_cookies import clear_refresh_cookie, set_refresh_cookie
from app.api.auth_dependencies import get_current_user
from app.api.schemas import (
    AuthProvidersOut,
    AuthSessionListOut,
    AuthSessionOut,
    CurrentUserOut,
    LoginRequest,
    LoginResponse,
    OAuthSignInRequest,
    OrganizationMembershipOut,
    OrganizationOut,
    RefreshResponse,
    SessionRevokeAllOut,
    SignupRequest,
    UserOut,
)
from app.config import Settings, get_settings
from app.db.models import AuthSession, Organization, User
from app.db.session import get_session
from app.services import audit
from app.services.auth import (
    audit_context,
    authenticate_user,
    authenticate_with_identity,
    create_user,
    get_user_by_email,
)
from app.services.auth_sessions import (
    InvalidRefreshSessionError,
    RefreshTokenReuseDetectedError,
    list_active_sessions_for_user,
    revoke_other_sessions_for_user,
    revoke_refresh_session_family,
    revoke_session_family_for_user,
    rotate_refresh_session,
    start_refresh_session,
)
from app.services.oauth import (
    OAuthConfigurationError,
    OAuthTokenError,
    verify_id_token,
)
from app.services.permissions import permissions_for
from app.services.tenancy import (
    OrgContext,
    OrgScopeRequired,
    memberships_for_user,
    resolve_org_context,
)
from app.services.tokens import (
    TokenConfigurationError,
    TokenType,
    TokenValidationError,
    decode_token,
    hash_refresh_jti,
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


@router.get(
    "/providers",
    response_model=AuthProvidersOut,
)
def auth_providers(
    settings: Settings = Depends(get_settings),
) -> AuthProvidersOut:
    """Which provider sign-ins this deployment can actually complete.

    Public because the sign-in form is: the page that needs this is the one
    nobody has signed into yet. It discloses only client ids, which the browser
    hands to the provider on every sign-in anyway.
    """

    return AuthProvidersOut(
        google=settings.google_client_id.strip() or None,
        apple=settings.apple_client_id.strip() or None,
    )


@router.post(
    "/oauth",
    response_model=LoginResponse,
)
def oauth_sign_in(
    payload: OAuthSignInRequest,
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    """Sign in with a Google or Apple identity token, registering on first use.

    Deliberately one endpoint rather than an OAuth twin of ``/signup`` and
    ``/login``: the provider flow has a single button behind it, and which of the
    two happened is something only the server can know. Everything after the
    token is verified — the session family, the rotating refresh cookie, the
    access token — is the machinery ``/login`` already uses, unchanged.
    """

    try:
        identity = verify_id_token(
            provider=payload.provider,
            id_token=payload.id_token,
            settings=settings,
        )
    except OAuthConfigurationError as exc:
        # Ours to fix, not the caller's: an unconfigured provider and an
        # unreachable key set are both "we cannot answer right now".
        raise _authentication_unavailable() from exc
    except OAuthTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid identity token",
        ) from exc

    try:
        user = authenticate_with_identity(
            session,
            identity,
            account_type=payload.account_type,
            organization_name=payload.organization_name,
        )
    except IntegrityError as exc:
        # The race where two sign-ins register the same identity at once, the
        # same one ``/signup`` guards against on the email.
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="account already registered",
        ) from exc

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid identity token",
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
    x_org_id: Annotated[str | None, Header(alias="X-Org-Id")] = None,
) -> CurrentUserOut:
    """Who you are, which organization you are acting in, and what you may do.

    The role and permission list ride along so the UI can hide a control the
    caller cannot use, instead of showing it and failing on click. They are for
    RENDERING ONLY — every endpoint enforces its own permission independently,
    so a client that lies about this list gets a 403 exactly as before.

    ``X-Org-Id`` selects which org the singular ``organization``/``role``/
    ``permissions`` describe, so a multi-org user who has switched sees the org
    they switched to rather than always their first. Membership is verified, not
    trusted — the same seam ``get_org_context`` uses — and honouring the header
    is additive: omitting it reproduces the old behaviour exactly. ``organizations``
    always carries the caller's full list, which is what makes a switch offerable.
    """

    requested_org_id: uuid.UUID | None = None
    if x_org_id:
        try:
            requested_org_id = uuid.UUID(x_org_id)
        except ValueError:
            requested_org_id = None

    organization = None
    role = None
    permissions: list[str] = []
    context = _resolve_me_context(session, current_user, requested_org_id)
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
        organizations=_organization_memberships(session, current_user),
    )


@router.get(
    "/sessions",
    response_model=AuthSessionListOut,
)
def list_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AuthSessionListOut:
    """The caller's own active sessions, one per device/login.

    A read, so it emits no audit event. The one from the current device is
    flagged ``current`` by matching the refresh cookie riding along on this
    request (the cookie's path covers ``/api/v1/auth``) to its session family.
    """

    current_family = _current_family_id(session, request, settings)
    summaries = list_active_sessions_for_user(
        session,
        user_id=current_user.id,
        current_family_id=current_family,
    )
    return AuthSessionListOut(
        sessions=[AuthSessionOut.model_validate(summary) for summary in summaries],
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    """Revoke one of the caller's own sessions (a whole family).

    Strictly self-scoped. A session id that is not the caller's — whether it
    belongs to another user or does not exist — is a 404 with the same body in
    both cases, so this cannot be used to probe whether a given session id
    exists. The revocation is audited only when something was actually revoked.
    """

    revoked = revoke_session_family_for_user(
        session,
        user_id=current_user.id,
        family_id=session_id,
    )
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="session not found",
        )

    audit.emit(
        session,
        action="auth:session_revoke",
        context=audit_context(session, current_user),
        actor_type="user",
        actor_id=current_user.id,
        actor_label=current_user.email,
        entity_type="auth_session",
        entity_id=session_id,
    )
    session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/sessions/revoke-all",
    response_model=SessionRevokeAllOut,
)
def revoke_all_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SessionRevokeAllOut:
    """Sign out everywhere else, keeping the current session alive.

    See ``revoke_other_sessions_for_user`` for why the current device is spared.
    Always audited — a lock-out of every other device is exactly the event worth
    recording — even when there was nothing else to revoke.
    """

    current_family = _current_family_id(session, request, settings)
    revoked = revoke_other_sessions_for_user(
        session,
        user_id=current_user.id,
        keep_family_id=current_family,
    )

    audit.emit(
        session,
        action="auth:session_revoke_all",
        context=audit_context(session, current_user),
        actor_type="user",
        actor_id=current_user.id,
        actor_label=current_user.email,
        entity_type="user",
        entity_id=current_user.id,
        # Not "sessions_revoked": the audit redactor matches the substring
        # "session" and would replace the count with "[redacted]" — the
        # redactor being over-eager exactly as designed. The fix is the key
        # name here, the same move admin_routes makes for the same reason.
        detail={"devices_signed_out": revoked, "kept_current": current_family is not None},
    )
    session.commit()

    return SessionRevokeAllOut(revoked=revoked, kept_current=current_family is not None)


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


def _resolve_me_context(
    session: Session,
    user: User,
    org_id: uuid.UUID | None,
) -> OrgContext | None:
    """The org ``/me`` should describe, tolerating a stale or unknown ``org_id``.

    A user with no organization can still see who they are, so an empty result is
    ``None`` rather than a failed call. A *named* org that is not theirs (a stale
    or forged ``X-Org-Id``) falls back to their default org instead of 403-ing —
    ``/me`` is render-only, and losing access to the org you last switched to
    should degrade to "your first org", not break the whole session.
    """

    try:
        return resolve_org_context(session, user=user, org_id=org_id)
    except OrgScopeRequired:
        if org_id is None:
            return None
        try:
            return resolve_org_context(session, user=user)
        except OrgScopeRequired:
            return None


def _organization_memberships(
    session: Session,
    user: User,
) -> list[OrganizationMembershipOut]:
    """The caller's full org list for the switcher — each with their role in it."""

    memberships = []
    for membership in memberships_for_user(session, user.id):
        org = session.get(Organization, membership.org_id)
        if org is None:  # pragma: no cover - a membership implies its org exists
            continue
        memberships.append(
            OrganizationMembershipOut(
                id=org.id,
                name=org.name,
                slug=org.slug,
                kind=org.kind,
                status=org.status,
                role=membership.role,
            )
        )
    return memberships


def _current_family_id(
    session: Session,
    request: Request,
    settings: Settings,
) -> uuid.UUID | None:
    """The session family the request's refresh cookie belongs to, or ``None``.

    Used to flag the caller's current session and to spare it from
    "sign out everywhere else". A missing, malformed, unknown, or wrong-user
    cookie simply yields ``None`` — the endpoints treat "cannot identify the
    current session" as "there is no current session to protect", which is the
    safe direction.
    """

    refresh_token = request.cookies.get(settings.auth_refresh_cookie_name)
    if refresh_token is None:
        return None

    try:
        claims = decode_token(
            refresh_token,
            expected_type=TokenType.REFRESH,
            settings=settings,
        )
    except (TokenValidationError, TokenConfigurationError):
        return None

    row = session.scalar(
        select(AuthSession).where(
            AuthSession.refresh_jti_hash == hash_refresh_jti(claims.jti, settings=settings),
        )
    )
    if row is None or row.user_id != claims.user_id:
        return None
    return row.family_id


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
