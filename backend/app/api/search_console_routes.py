"""The Google Search Console connection surface (Phase 9 / P9.2).

Two routers, because the two halves of an OAuth flow have genuinely different
callers and cannot share a dependency stack.

**The connect route is ordinary authenticated API.** It is nested under a
project like the backlink routes are, takes a bearer token, resolves an
``OrgContext``, and names the permission it needs. It is the only place the
caller's identity is known, which is why it is the place that writes that
identity down.

**The callback route is the browser coming back from Google, and it cannot
authenticate.** The access token lives in the frontend's memory; a full-page
redirect from ``accounts.google.com`` carries no Authorization header and no
usable cookie. So the callback takes no auth dependency at all and recovers who
it is acting for from the state row alone. Every alternative — trusting a query
parameter, trusting the ID token's email, adding a cookie — hands an attacker a
way to attach their own Google account to somebody else's project.

Both are dark behind ``GSC_ENABLED`` with a 404 rather than a 403, the shape
``backlink_routes.py`` established: a refusal that says "forbidden" has still
confirmed the feature exists.

The callback never renders a body. It always redirects to a URL this module
builds from the state row, with a reason drawn from a fixed allowlist — so
neither the destination nor the message can be influenced by the request.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.org_dependencies import requires
from app.api.search_console_schemas import SearchConsoleConnectStartOut
from app.config import Settings, get_settings
from app.db.session import get_session
from app.gsc.base import GoogleIdentityError, GoogleOAuthError, GoogleOAuthProvider
from app.gsc.registry import get_google_oauth_provider
from app.services import audit, search_console
from app.services.permissions import GSC_CONNECT
from app.services.seo_projects import get_org_project
from app.services.tenancy import OrgContext

# The complete set of outcomes a browser may be told about. A closed set rather
# than a formatted string: everything here reaches a URL, and the alternative is
# reflecting provider text — or an exception message — into the address bar.
CallbackReason = Literal[
    "access_denied",
    "invalid_state",
    "expired_state",
    "provider_error",
    "invalid_identity",
    "missing_refresh_token",
]


def require_gsc_enabled(settings: Annotated[Settings, Depends(get_settings)]) -> None:
    """404 the whole module while the kill switch is off."""

    if not settings.gsc_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def get_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> GoogleOAuthProvider:
    """The configured Google client, as a dependency.

    A dependency rather than a plain call so tests can substitute the
    deterministic mock through ``app.dependency_overrides`` — which is what
    guarantees the suite cannot reach Google even if a settings flag is wrong.
    """

    provider = get_google_oauth_provider(settings)
    if provider is None:  # pragma: no cover - require_gsc_enabled already 404s
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return provider


router = APIRouter(
    prefix="/api/v1/seo-projects/{project_id}/search-console",
    tags=["search-console"],
    dependencies=[Depends(require_gsc_enabled)],
)

callback_router = APIRouter(
    prefix="/api/v1/integrations/google-search-console",
    tags=["search-console"],
    dependencies=[Depends(require_gsc_enabled)],
)


@router.post(
    "/connect",
    response_model=SearchConsoleConnectStartOut,
    status_code=status.HTTP_201_CREATED,
)
def start_search_console_connect(
    project_id: uuid.UUID,
    org: Annotated[OrgContext, Depends(requires(GSC_CONNECT))],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[GoogleOAuthProvider, Depends(get_provider)],
) -> SearchConsoleConnectStartOut:
    """Begin an authorization attempt and return where to send the browser.

    201 rather than 200: this creates a short-lived, single-use attempt. The
    response deliberately carries nothing but the URL — the state, nonce and
    PKCE verifier stay server-side, and only the state's hash is stored.
    """

    project = get_org_project(session, org_id=org.require_org_id, project_id=project_id)
    if project is None:
        # 404 whether it does not exist or is not theirs, matching the rest of
        # the project surface: distinguishing the two enumerates other tenants.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SEO project not found")

    started = search_console.start_authorization(
        session,
        settings=settings,
        provider=provider,
        org_id=org.require_org_id,
        user_id=org.require_user_id,
        seo_project_id=project.id,
    )

    audit.emit(
        session,
        action=GSC_CONNECT,
        context=org,
        actor_type="user",
        outcome="started",
        entity_type="seo_project",
        entity_id=project.id,
        detail={"step": "authorization_started"},
    )
    session.commit()

    return SearchConsoleConnectStartOut(authorization_url=started.authorization_url)


@callback_router.get("/callback", include_in_schema=False)
def complete_search_console_connect(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[GoogleOAuthProvider, Depends(get_provider)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Google's return leg. Never authenticated, never trusted beyond the state.

    Kept out of the OpenAPI schema on purpose: it is a browser redirect target
    registered with Google, not an interface the frontend calls, and publishing
    it in the generated client would invite exactly that.
    """

    if not state:
        # Nothing to attribute this to — not even a project to send them back
        # to. This is the one path that cannot land on a project page.
        return _redirect_without_project(settings, reason="invalid_state")

    try:
        claimed = search_console.consume_oauth_state(session, raw_state=state)
    except search_console.OAuthStateExpired:
        session.commit()
        return _redirect_without_project(settings, reason="expired_state")
    except search_console.OAuthStateInvalid:
        return _redirect_without_project(settings, reason="invalid_state")

    # From here the state is spent whatever happens next, so every exit commits.
    # A failed exchange must not leave a replayable attempt behind.
    project_id = claimed.seo_project_id

    if error:
        # The user declined, or Google refused. `error` is attacker-influenced
        # and is never echoed; only its presence is used.
        session.commit()
        return _redirect(settings, project_id=project_id, reason="access_denied")

    if not code:
        session.commit()
        return _redirect(settings, project_id=project_id, reason="provider_error")

    try:
        tokens = provider.exchange_code(code=code, code_verifier=claimed.code_verifier)
    except GoogleOAuthError:
        session.commit()
        return _redirect(settings, project_id=project_id, reason="provider_error")

    try:
        identity = search_console.verify_identity_for_state(
            provider=provider,
            tokens=tokens,
            claimed=claimed,
        )
    except GoogleIdentityError:
        session.commit()
        return _redirect(settings, project_id=project_id, reason="invalid_identity")
    except GoogleOAuthError:
        session.commit()
        return _redirect(settings, project_id=project_id, reason="provider_error")

    try:
        connection = search_console.upsert_google_connection(
            session,
            settings=settings,
            org_id=claimed.org_id,
            user_id=claimed.user_id,
            identity=identity,
            tokens=tokens,
        )
    except search_console.MissingRefreshToken:
        session.commit()
        return _redirect(settings, project_id=project_id, reason="missing_refresh_token")

    audit.emit(
        session,
        action=GSC_CONNECT,
        # Built from the state row rather than resolved from a request, because
        # this request has no caller. Role is empty on purpose: nothing here is
        # a permission decision — the permission was checked when the attempt
        # was created, and this context exists only to attribute the event.
        context=OrgContext(org_id=claimed.org_id, user_id=claimed.user_id),
        actor_type="user",
        outcome="success",
        entity_type="google_connection",
        entity_id=connection.id,
        # Google's opaque subject, which is an identifier and not a credential.
        # No token, refresh token or email is recorded here.
        detail={"step": "connected", "google_account_id": connection.google_account_id},
    )
    session.commit()

    return _redirect(settings, project_id=project_id, reason=None)


def _redirect(
    settings: Settings,
    *,
    project_id: uuid.UUID,
    reason: CallbackReason | None,
) -> RedirectResponse:
    """Build the one destination this flow is allowed to end at.

    The path is assembled from the project id **on the state row**, never from
    the request, and the origin comes from settings. There is no input to this
    function an attacker controls, which is what makes an open redirect
    impossible rather than merely unlikely.
    """

    query = {"gsc": "connected"} if reason is None else {"gsc": "error", "reason": reason}
    destination = (
        f"{settings.public_base_url.rstrip('/')}/site-audit/{project_id}?{urlencode(query)}"
    )
    return RedirectResponse(url=destination, status_code=status.HTTP_302_FOUND)


def _redirect_without_project(settings: Settings, *, reason: CallbackReason) -> RedirectResponse:
    """The fallback for a callback too broken to name a project."""

    query = urlencode({"gsc": "error", "reason": reason})
    destination = f"{settings.public_base_url.rstrip('/')}/site-audit?{query}"
    return RedirectResponse(url=destination, status_code=status.HTTP_302_FOUND)
