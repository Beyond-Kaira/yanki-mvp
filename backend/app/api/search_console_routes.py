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
from datetime import date
from typing import Annotated, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.org_dependencies import requires
from app.api.search_console_schemas import (
    ProjectConnectionStatus,
    SearchConsoleConnectionOut,
    SearchConsoleConnectionsOut,
    SearchConsoleConnectStartOut,
    SearchConsoleMetricsOut,
    SearchConsolePerformanceOut,
    SearchConsolePropertiesOut,
    SearchConsolePropertyLinkOut,
    SearchConsolePropertyLinkRequest,
    SearchConsolePropertyOut,
    SearchConsoleRowOut,
)
from app.config import Settings, get_settings
from app.db.models import GoogleConnection, SeoProject
from app.db.session import get_session
from app.gsc.base import (
    GoogleAccessForbidden,
    GoogleAuthorizationRevoked,
    GoogleIdentityError,
    GoogleOAuthError,
    GoogleOAuthProvider,
    GoogleProperty,
    GoogleRateLimited,
    GoogleResponseInvalid,
)
from app.gsc.registry import get_google_oauth_provider
from app.services import audit, search_console
from app.services.permissions import GSC_CONNECT, PROJECT_READ
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


def _project_or_404(session: Session, org: OrgContext, project_id: uuid.UUID) -> SeoProject:
    """404 whether it does not exist or is not theirs — never tell them apart."""

    project = get_org_project(session, org_id=org.require_org_id, project_id=project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SEO project not found")
    return project


def _connection_or_404(
    session: Session, org: OrgContext, connection_id: uuid.UUID
) -> GoogleConnection:
    """Same rule one level down: another org's connection simply does not exist."""

    connection = search_console.get_org_connection(
        session, org_id=org.require_org_id, connection_id=connection_id
    )
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="google connection not found"
        )
    return connection


def _fetch_properties(
    session: Session,
    *,
    settings: Settings,
    provider: GoogleOAuthProvider,
    connection: GoogleConnection,
) -> tuple[GoogleProperty, ...]:
    """Refresh a token and ask Google what this account can reach.

    The one place provider failures become HTTP, so every route that talks to
    Search Console reports the same thing for the same cause. Google's own
    response body reaches none of these — the exception types carry the whole
    distinction, and each maps to a different action:

    * revoked grant → 409, reconnect
    * lost property access → 409, choose a different property
    * rate limited → 429, wait (with Retry-After when Google gave one)
    * unreadable answer → 502, nothing the caller can do
    * unreachable → 503, try later
    """

    try:
        access_token = search_console.get_access_token(
            session, settings=settings, provider=provider, connection=connection
        )
        properties = provider.list_properties(access_token=access_token)
    except search_console.ReauthRequired as exc:
        session.commit()  # persist reauth_required before answering
        raise _conflict("reauth_required") from exc
    except GoogleAuthorizationRevoked as exc:
        session.commit()
        raise _conflict("reauth_required") from exc
    except GoogleAccessForbidden as exc:
        raise _conflict("property_access_lost") from exc
    except GoogleRateLimited as exc:
        raise _rate_limited(exc) from exc
    except GoogleResponseInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="malformed_provider_response"
        ) from exc
    except GoogleOAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="provider_unavailable"
        ) from exc

    session.commit()
    return properties


def _conflict(reason: str) -> HTTPException:
    """409 with a fixed reason code. Never a provider string."""

    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=reason)


def _rate_limited(exc: GoogleRateLimited) -> HTTPException:
    headers = (
        {"Retry-After": str(exc.retry_after_seconds)}
        if exc.retry_after_seconds is not None
        else None
    )
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="provider_rate_limited",
        headers=headers,
    )


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

    project = _project_or_404(session, org, project_id)

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


@router.get("/connections", response_model=SearchConsoleConnectionsOut)
def list_search_console_connections(
    project_id: uuid.UUID,
    org: Annotated[OrgContext, Depends(requires(PROJECT_READ))],
    session: Annotated[Session, Depends(get_session)],
) -> SearchConsoleConnectionsOut:
    """The organization's Google accounts, and where this project stands.

    A read, so ``project:read`` rather than ``gsc:connect`` — a Viewer may see
    that a project is connected without being able to change it. Nothing here
    calls Google: it is entirely local state, which is what makes it safe to
    poll and cheap to render.
    """

    project = _project_or_404(session, org, project_id)
    link = search_console.get_project_link(
        session, org_id=org.require_org_id, seo_project_id=project.id
    )
    connections = search_console.list_org_connections(session, org_id=org.require_org_id)

    selected_connection_id = link.google_connection_id if link is not None else None

    rows = [
        SearchConsoleConnectionOut(
            id=connection.id,
            google_account_email=connection.google_account_email,
            status=connection.status,
            # The column is one canonical space-delimited string; a client wants
            # a list. This is the only reshaping the connection surface does.
            scopes=connection.scopes.split(),
            created_at=connection.created_at,
            updated_at=connection.updated_at,
            selected_for_project=connection.id == selected_connection_id,
            selected_site_url=(
                link.site_url
                if link is not None and connection.id == selected_connection_id
                else None
            ),
        )
        for connection in connections
    ]

    selected = next((row for row in rows if row.selected_for_project), None)
    project_status: ProjectConnectionStatus
    if not rows:
        project_status = "no_connection"
    elif selected is None:
        # Either nothing is linked, or the link pointed at a connection this
        # organization cannot see. Both are reported as "choose a property",
        # which is the honest instruction and leaks nothing about the other.
        project_status = "no_property_selected"
    elif selected.status == "reauth_required":
        project_status = "reauth_required"
    else:
        project_status = "connected"

    return SearchConsoleConnectionsOut(project_status=project_status, connections=rows)


@router.get(
    "/connections/{connection_id}/properties",
    response_model=SearchConsolePropertiesOut,
)
def list_search_console_properties(
    project_id: uuid.UUID,
    connection_id: uuid.UUID,
    org: Annotated[OrgContext, Depends(requires(GSC_CONNECT))],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[GoogleOAuthProvider, Depends(get_provider)],
) -> SearchConsolePropertiesOut:
    """What this Google account can reach, ordered so the obvious choice is first.

    ``gsc:connect`` rather than ``project:read``: this spends a token refresh
    and a Search Console call on every request, and it is the list a user picks
    from — both belong to the role that may change the connection.
    """

    project = _project_or_404(session, org, project_id)
    connection = _connection_or_404(session, org, connection_id)
    link = search_console.get_project_link(
        session, org_id=org.require_org_id, seo_project_id=project.id
    )

    properties = _fetch_properties(
        session, settings=settings, provider=provider, connection=connection
    )

    offered = search_console.offer_properties(
        properties,
        project_domain_key=project.domain_key,
        selected_site_url=(
            link.site_url
            if link is not None and link.google_connection_id == connection.id
            else None
        ),
    )

    return SearchConsolePropertiesOut(
        google_connection_id=connection.id,
        google_account_email=connection.google_account_email,
        properties=[
            SearchConsolePropertyOut(
                site_url=item.site_url,
                permission_level=item.permission_level,
                property_type=item.property_type,  # type: ignore[arg-type]
                matches_project_domain=item.matches_project_domain,
                currently_selected=item.currently_selected,
            )
            for item in offered
        ],
    )


@router.put("/property", response_model=SearchConsolePropertyLinkOut)
def link_search_console_property(
    project_id: uuid.UUID,
    payload: SearchConsolePropertyLinkRequest,
    org: Annotated[OrgContext, Depends(requires(GSC_CONNECT))],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[GoogleOAuthProvider, Depends(get_provider)],
) -> SearchConsolePropertyLinkOut:
    """Point this project at one property, or move it to a different one.

    The live property list is fetched again here rather than trusted from
    whatever the client saw. Between rendering a picker and submitting it, access
    can be removed in Search Console — and more to the point, the request is just
    a string a caller can write. ``permission_level`` comes from the match, so
    the stored row records what Google says rather than what was claimed.
    """

    project = _project_or_404(session, org, project_id)
    connection = _connection_or_404(session, org, payload.google_connection_id)

    properties = _fetch_properties(
        session, settings=settings, provider=provider, connection=connection
    )

    try:
        link = search_console.link_property(
            session,
            seo_project_id=project.id,
            connection=connection,
            site_url=payload.site_url,
            available=properties,
            user_id=org.user_id,
        )
    except search_console.PropertyNotAccessible as exc:
        raise _conflict("property_not_accessible") from exc

    audit.emit(
        session,
        action=GSC_CONNECT,
        context=org,
        actor_type="user",
        outcome="success",
        entity_type="seo_project",
        entity_id=project.id,
        detail={"step": "property_linked", "site_url": link.site_url},
    )
    session.commit()

    return SearchConsolePropertyLinkOut(
        google_connection_id=connection.id,
        google_account_email=connection.google_account_email,
        site_url=link.site_url,
        property_type=link.property_type,  # type: ignore[arg-type]
        permission_level=link.permission_level,
        connected_at=link.created_at,
        updated_at=link.updated_at,
    )


@router.delete("/property", status_code=status.HTTP_204_NO_CONTENT)
def unlink_search_console_property(
    project_id: uuid.UUID,
    org: Annotated[OrgContext, Depends(requires(GSC_CONNECT))],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """Stop reporting Search Console for this project.

    Idempotent: unlinking something already unlinked is a success, because the
    caller's intent — "this project has no property" — is equally true either
    way. The ``GoogleConnection`` is untouched; it is shared with the
    organization's other projects, and signing them all out of Google is not
    what was asked.
    """

    project = _project_or_404(session, org, project_id)
    removed = search_console.unlink_property(session, seo_project_id=project.id)

    if removed:
        audit.emit(
            session,
            action=GSC_CONNECT,
            context=org,
            actor_type="user",
            outcome="success",
            entity_type="seo_project",
            entity_id=project.id,
            detail={"step": "property_unlinked"},
        )
    session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/performance", response_model=SearchConsolePerformanceOut)
def get_search_console_performance(
    project_id: uuid.UUID,
    org: Annotated[OrgContext, Depends(requires(PROJECT_READ))],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[GoogleOAuthProvider, Depends(get_provider)],
    start_date: date | None = None,
    end_date: date | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> SearchConsolePerformanceOut:
    """Live Search Console performance for the linked property.

    Fetched synchronously on every request and cached nowhere. That is a
    deliberate MVP decision, not an oversight: caching means choosing a staleness
    policy and owning an invalidation bug, and there is no evidence yet about how
    often this is read. It is bounded instead — three queries, a row cap, and a
    timeout — so the worst case is knowable.
    """

    project = _project_or_404(session, org, project_id)
    link = search_console.get_project_link(
        session, org_id=org.require_org_id, seo_project_id=project.id
    )
    if link is None:
        raise _conflict("no_property_selected")

    connection = search_console.get_org_connection(
        session, org_id=org.require_org_id, connection_id=link.google_connection_id
    )
    if connection is None:
        # A link whose connection is not visible in this organization. Fail
        # closed and describe it as an unselected property rather than
        # confirming that some other tenant's row exists.
        raise _conflict("no_property_selected")
    if connection.status == "reauth_required":
        raise _conflict("reauth_required")

    try:
        start, end = search_console.validate_date_range(start_date, end_date)
    except search_console.InvalidDateRange as exc:
        # Bare 422 to match backlink_routes.py; the named constant was renamed
        # under us and the number is the stable thing.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        access_token = search_console.get_access_token(
            session, settings=settings, provider=provider, connection=connection
        )
        report = search_console.build_performance_report(
            provider=provider,
            access_token=access_token,
            site_url=link.site_url,
            start=start,
            end=end,
            row_limit=search_console.clamp_row_limit(limit),
        )
    except search_console.ReauthRequired as exc:
        session.commit()
        raise _conflict("reauth_required") from exc
    except GoogleAuthorizationRevoked as exc:
        session.commit()
        raise _conflict("reauth_required") from exc
    except GoogleAccessForbidden as exc:
        raise _conflict("property_access_lost") from exc
    except GoogleRateLimited as exc:
        raise _rate_limited(exc) from exc
    except GoogleResponseInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="malformed_provider_response"
        ) from exc
    except GoogleOAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="provider_unavailable"
        ) from exc

    session.commit()

    return SearchConsolePerformanceOut(
        site_url=report.site_url,
        start_date=report.start_date,
        end_date=report.end_date,
        data_state=report.data_state,  # type: ignore[arg-type]
        summary=SearchConsoleMetricsOut(
            clicks=report.summary.clicks,
            impressions=report.summary.impressions,
            ctr=report.summary.ctr,
            position=report.summary.position,
        ),
        top_queries=[
            SearchConsoleRowOut(
                key=row.key,
                clicks=row.clicks,
                impressions=row.impressions,
                ctr=row.ctr,
                position=row.position,
            )
            for row in report.top_queries
        ],
        top_pages=[
            SearchConsoleRowOut(
                key=row.key,
                clicks=row.clicks,
                impressions=row.impressions,
                ctr=row.ctr,
                position=row.position,
            )
            for row in report.top_pages
        ],
    )


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
