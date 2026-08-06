"""Orchestration for connecting a Google account to a Site Audit project.

The router owns HTTP and the provider owns Google; this owns the part that is
neither — what is written down, in what order, and what happens when a step
fails. Three properties are the reason it is a separate module.

**Identity comes from the state row, never from the callback.** The browser
returns from Google with no session: the access token lives in the frontend's
memory and a full-page redirect cannot carry it. So the authenticated request
that *starts* the flow records the organization, the user and the project, and
the callback reads them back by state. Every alternative — a query parameter, a
cookie, trusting the ID token's email — lets a caller attach their own Google
account to a project that is not theirs.

**A state is claimed, not checked.** :func:`consume_oauth_state` is a
conditional UPDATE, so "is it live?" and "mark it used" are one operation. A
read-then-write would let two callbacks carrying the same state both pass the
read before either wrote, which is precisely the replay the state exists to
stop.

**A reconnect never destroys what it cannot replace.** Google omits the refresh
token whenever it decides a grant already exists, so an upsert that wrote
whatever arrived would turn a working connection into an unusable one. The
existing ciphertext is kept in that case, and a *first* connection with no
refresh token is refused outright rather than stored broken.

Nothing here logs a raw state, nonce, code or token.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy import CursorResult
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import (
    GoogleConnection,
    GoogleOAuthState,
    SiteAuditSearchConsoleLink,
)
from app.gsc.base import (
    GoogleAuthorizationRevoked,
    GoogleIdentity,
    GoogleIdentityError,
    GoogleOAuthError,
    GoogleOAuthProvider,
    GoogleProperty,
    GoogleTokens,
    SearchAnalyticsRow,
)
from app.gsc.normalize import matches_project_domain, parse_property, property_type_of
from app.services.token_crypto import decrypt_secret, encrypt_secret

# 32 bytes of entropy each, url-safe. The state and nonce travel in a URL and
# the verifier must be 43-128 characters per RFC 7636; token_urlsafe(32) yields
# 43, the minimum that satisfies it.
_ENTROPY_BYTES = 32

# Search Console reports on Pacific days regardless of where the property or the
# reader is, so "yesterday" has to be asked of that clock or the last day in a
# range is sometimes empty and sometimes not.
SEARCH_CONSOLE_TIMEZONE = ZoneInfo("America/Los_Angeles")

# Google keeps revising the most recent days for roughly this long. Ending a
# default range at "yesterday" would show numbers that quietly change on reload;
# ending it here means the default report is stable once seen.
FINALIZED_DATA_LAG_DAYS = 3
DEFAULT_LOOKBACK_DAYS = 28

# Google itself retains ~16 months. A wider request is not a bigger report, it
# is a slower one that returns the same thing.
MAX_RANGE_DAYS = 480

MIN_ROW_LIMIT = 1
MAX_ROW_LIMIT = 100
DEFAULT_ROW_LIMIT = 25

# A property nobody has verified cannot be queried, so offering it would be
# offering a choice that fails on use.
UNUSABLE_PERMISSION_LEVELS = frozenset({"siteUnverifiedUser"})


class SearchConsoleError(RuntimeError):
    """Base for failures the router turns into a specific outcome."""


class OAuthStateInvalid(SearchConsoleError):
    """No live state matched — unknown, already consumed, or never existed."""


class OAuthStateExpired(SearchConsoleError):
    """The state existed and its window had closed."""


class MissingRefreshToken(SearchConsoleError):
    """Google returned no refresh token and none is already stored."""


class ReauthRequired(SearchConsoleError):
    """The stored grant is dead. Only the user reconnecting fixes it."""


class NoPropertySelected(SearchConsoleError):
    """The project has no Search Console property linked yet."""


class PropertyNotAccessible(SearchConsoleError):
    """The requested property is not one this account can actually reach.

    Raised when a caller names a ``site_url`` that is absent from the live list
    Google just returned. The request is refused rather than trusted, because
    the alternative is storing a link to a property the account cannot query and
    discovering it later as an empty report.
    """


class InvalidDateRange(SearchConsoleError):
    """The requested window is backwards, in the future, or absurdly wide."""


@dataclass(frozen=True, slots=True)
class StartedAuthorization:
    """What the connect endpoint hands back. Contains no secret."""

    authorization_url: str


@dataclass(frozen=True, slots=True)
class ClaimedState:
    """A state row that this call, and only this call, consumed."""

    id: uuid.UUID
    org_id: uuid.UUID
    user_id: uuid.UUID
    seo_project_id: uuid.UUID
    code_verifier: str
    nonce_hash: str


def hash_oauth_value(raw: str) -> str:
    """SHA-256 of a state or nonce, hex encoded.

    Plain SHA-256 rather than a keyed HMAC, matching ``Invitation.token_hash``:
    these values carry 32 bytes of entropy, so there is no dictionary to attack
    and a key would add a rotation hazard without adding a guarantee.
    """

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def code_challenge_for(code_verifier: str) -> str:
    """The S256 PKCE challenge: base64url(sha256(verifier)), unpadded."""

    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def canonical_scopes(raw_scope: str) -> str:
    """One representation for one granted set.

    Space-delimited and sorted. Space-delimited because that is what OAuth 2.0
    puts on the wire and what Google returns, so the stored value stays
    comparable to its source without a parse step; sorted because Google does
    not promise an order, and an unsorted store would make the same grant look
    like two different grants across reconnects — which is the kind of
    difference that later shows up as a spurious "scopes changed" alert.
    """

    return " ".join(sorted({part for part in raw_scope.split() if part}))


def purge_expired_states(session: Session, *, now: datetime | None = None) -> int:
    """Delete states past their window. Opportunistic, called on connect.

    A sweep on write rather than a scheduled job: the table only grows when
    somebody starts a flow, so the moment a row is added is exactly the moment
    the stale ones are worth removing, and it needs no worker to be deployed.
    """

    moment = now or datetime.now(UTC)
    # cast: Session.execute is typed as returning Result, but DML returns a
    # CursorResult, which is where rowcount lives.
    result = cast(
        "CursorResult[Any]",
        session.execute(sa.delete(GoogleOAuthState).where(GoogleOAuthState.expires_at <= moment)),
    )
    return int(result.rowcount or 0)


def start_authorization(
    session: Session,
    *,
    settings: Settings,
    provider: GoogleOAuthProvider,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    seo_project_id: uuid.UUID,
    now: datetime | None = None,
) -> StartedAuthorization:
    """Mint one authorization attempt and return the URL to send the browser to.

    The raw state and nonce exist only in the returned URL. The database gets
    their hashes, and the caller gets no way to read them back.
    """

    moment = now or datetime.now(UTC)
    purge_expired_states(session, now=moment)

    state = secrets.token_urlsafe(_ENTROPY_BYTES)
    nonce = secrets.token_urlsafe(_ENTROPY_BYTES)
    code_verifier = secrets.token_urlsafe(_ENTROPY_BYTES)

    session.add(
        GoogleOAuthState(
            state_hash=hash_oauth_value(state),
            nonce_hash=hash_oauth_value(nonce),
            code_verifier=code_verifier,
            org_id=org_id,
            user_id=user_id,
            seo_project_id=seo_project_id,
            created_at=moment,
            expires_at=moment + timedelta(seconds=settings.gsc_oauth_state_ttl_seconds),
        )
    )
    session.flush()

    return StartedAuthorization(
        authorization_url=provider.authorization_url(
            state=state,
            nonce=nonce,
            code_challenge=code_challenge_for(code_verifier),
        )
    )


def consume_oauth_state(
    session: Session,
    *,
    raw_state: str,
    now: datetime | None = None,
) -> ClaimedState:
    """Atomically claim one live state, or raise.

    The UPDATE's WHERE clause *is* the claim: only a row that is unconsumed and
    unexpired can be marked, so two concurrent callbacks carrying the same state
    cannot both succeed. Only after it fails is the row read again, to tell an
    expired attempt from an unknown or replayed one — a distinction that costs
    one SELECT and is worth it, because "your connection attempt timed out" and
    "that link is not valid" send a user to different actions.
    """

    moment = now or datetime.now(UTC)
    state_hash = hash_oauth_value(raw_state)

    claimed = cast(
        "CursorResult[Any]",
        session.execute(
            sa.update(GoogleOAuthState)
            .where(
                GoogleOAuthState.state_hash == state_hash,
                GoogleOAuthState.consumed_at.is_(None),
                GoogleOAuthState.expires_at > moment,
            )
            .values(consumed_at=moment)
        ),
    )

    if not claimed.rowcount:
        existing = session.scalar(
            sa.select(GoogleOAuthState).where(GoogleOAuthState.state_hash == state_hash)
        )
        if existing is not None and existing.consumed_at is None:
            raise OAuthStateExpired("this authorization attempt has expired")
        raise OAuthStateInvalid("no live authorization attempt matches this state")

    row = session.scalar(
        sa.select(GoogleOAuthState).where(GoogleOAuthState.state_hash == state_hash)
    )
    if row is None:  # pragma: no cover - the UPDATE above just matched it
        raise OAuthStateInvalid("no live authorization attempt matches this state")

    return ClaimedState(
        id=row.id,
        org_id=row.org_id,
        user_id=row.user_id,
        seo_project_id=row.seo_project_id,
        code_verifier=row.code_verifier,
        nonce_hash=row.nonce_hash,
    )


def verify_identity_for_state(
    *,
    provider: GoogleOAuthProvider,
    tokens: GoogleTokens,
    claimed: ClaimedState,
) -> GoogleIdentity:
    """Verify the ID token, then bind it to the attempt that started this flow.

    Two steps, and the order matters. The provider proves the token is genuine —
    signature, issuer, audience, expiry — and hands back its ``nonce`` claim.
    Only then is that claim hashed and compared against the row, because the
    database never held the raw nonce. An ID token that is perfectly valid but
    was minted for some other authorization request fails here, which is the
    whole reason the nonce column exists.

    The comparison is constant-time. The values are hex digests rather than
    secrets, so this is cheap insurance rather than a strict necessity — but a
    timing-variable compare on an identity check is not a thing worth defending
    later.
    """

    identity = provider.verify_identity(id_token=tokens.id_token)

    if not identity.nonce:
        raise GoogleIdentityError("google id token carried no nonce")

    if not hmac.compare_digest(hash_oauth_value(identity.nonce), claimed.nonce_hash):
        raise GoogleIdentityError("google id token nonce did not match this attempt")

    return identity


def upsert_google_connection(
    session: Session,
    *,
    settings: Settings,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    identity: GoogleIdentity,
    tokens: GoogleTokens,
    now: datetime | None = None,
) -> GoogleConnection:
    """Create or refresh one connection, keyed by (org, Google subject).

    Scoped to that pair on purpose: a second Google account in the same
    organization is a second row, never an overwrite, because an agency holds
    one account per client estate and losing one to connect another is the
    failure this schema was shaped to prevent.
    """

    moment = now or datetime.now(UTC)

    connection = session.scalar(
        sa.select(GoogleConnection).where(
            GoogleConnection.org_id == org_id,
            GoogleConnection.google_account_id == identity.subject,
        )
    )

    if connection is None:
        if not tokens.refresh_token:
            # Refusing to write is the point. A connection with no refresh token
            # works until the access token expires in an hour and then fails
            # forever, and it would look connected the whole time.
            raise MissingRefreshToken("google returned no refresh token for a new connection")

        connection = GoogleConnection(
            org_id=org_id,
            google_account_id=identity.subject,
            google_account_email=identity.email,
            scopes=canonical_scopes(tokens.scope),
            status="active",
            refresh_token_ciphertext=encrypt_secret(tokens.refresh_token, settings=settings),
            connected_by_user_id=user_id,
            created_at=moment,
            updated_at=moment,
            last_refreshed_at=moment,
        )
        session.add(connection)
        session.flush()
        return connection

    connection.google_account_email = identity.email
    connection.scopes = canonical_scopes(tokens.scope)
    connection.status = "active"
    connection.connected_by_user_id = user_id
    connection.updated_at = moment

    if tokens.refresh_token:
        connection.refresh_token_ciphertext = encrypt_secret(
            tokens.refresh_token, settings=settings
        )
        connection.last_refreshed_at = moment
    # else: Google considered the existing grant sufficient and sent none. The
    # stored ciphertext is still the valid one, so it is left exactly as it is.

    session.flush()
    return connection


# ---------------------------------------------------------------------------
# Reading connections and links
# ---------------------------------------------------------------------------


def list_org_connections(session: Session, *, org_id: uuid.UUID) -> list[GoogleConnection]:
    """Every Google account this organization has connected, oldest first."""

    return list(
        session.scalars(
            sa.select(GoogleConnection)
            .where(GoogleConnection.org_id == org_id)
            .order_by(GoogleConnection.created_at, GoogleConnection.id)
        )
    )


def get_org_connection(
    session: Session, *, org_id: uuid.UUID, connection_id: uuid.UUID
) -> GoogleConnection | None:
    """One connection, scoped by organization.

    The org predicate is on the query rather than checked afterwards, so there
    is no shape of this call that reads another tenant's row first and decides
    about it second.
    """

    return session.scalar(
        sa.select(GoogleConnection).where(
            GoogleConnection.id == connection_id,
            GoogleConnection.org_id == org_id,
        )
    )


def get_project_link(
    session: Session, *, org_id: uuid.UUID, seo_project_id: uuid.UUID
) -> SiteAuditSearchConsoleLink | None:
    """The property linked to a project, or None.

    Joined to ``google_connections`` on the organization, so a link whose
    connection belongs to somebody else resolves to None rather than to a row.
    A foreign-key cascade should make that impossible; this makes it impossible
    to *read* even if it somehow is not, which is the difference between an
    invariant and a defence.
    """

    return session.scalar(
        sa.select(SiteAuditSearchConsoleLink)
        .join(
            GoogleConnection,
            GoogleConnection.id == SiteAuditSearchConsoleLink.google_connection_id,
        )
        .where(
            SiteAuditSearchConsoleLink.seo_project_id == seo_project_id,
            GoogleConnection.org_id == org_id,
        )
    )


# ---------------------------------------------------------------------------
# Access tokens
# ---------------------------------------------------------------------------


def get_access_token(
    session: Session,
    *,
    settings: Settings,
    provider: GoogleOAuthProvider,
    connection: GoogleConnection,
    now: datetime | None = None,
) -> str:
    """Exchange the stored refresh token for a short-lived access token.

    The access token is returned, never stored: it lives for the rest of one
    request and dies with it. Persisting it would buy an hour of latency and
    inherit a permanent obligation to encrypt, rotate and expire it.

    A refusal from Google is recorded on the connection as ``reauth_required``
    and re-raised as :class:`ReauthRequired`. That write matters — it is what
    lets the connections list tell a user *why* nothing works, instead of
    showing a healthy-looking row that fails on every use.
    """

    moment = now or datetime.now(UTC)

    refresh_token = decrypt_secret(
        connection.refresh_token_ciphertext,
        settings=settings,
        key_version=connection.encryption_key_version,
    )

    try:
        issued = provider.refresh_access_token(refresh_token=refresh_token)
    except GoogleAuthorizationRevoked as exc:
        connection.status = "reauth_required"
        connection.updated_at = moment
        session.flush()
        raise ReauthRequired("this google connection needs to be reconnected") from exc

    # A connection that was previously broken and now refreshes is working
    # again, so the flag clears itself rather than needing a manual reset.
    connection.status = "active"
    connection.last_refreshed_at = moment
    connection.updated_at = moment
    session.flush()

    return issued.access_token


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OfferedProperty:
    """One property as the API offers it, already reduced and judged."""

    site_url: str
    permission_level: str
    property_type: str
    matches_project_domain: bool
    currently_selected: bool


def usable_properties(properties: tuple[GoogleProperty, ...]) -> list[GoogleProperty]:
    """Drop the entries that cannot actually be queried.

    Only unverified ownership is filtered. An unfamiliar permission string is
    kept: Google adds levels over time, and hiding a property because its label
    is new would be a worse failure than showing one that later errors.
    """

    return [
        candidate
        for candidate in properties
        if parse_property(candidate.site_url) is not None
        and candidate.permission_level not in UNUSABLE_PERMISSION_LEVELS
    ]


def offer_properties(
    properties: tuple[GoogleProperty, ...],
    *,
    project_domain_key: str,
    selected_site_url: str | None,
) -> list[OfferedProperty]:
    """Order and annotate the list a user picks from.

    Suggested first, then whatever is already linked, then everything else
    alphabetically. Sorting is total and deterministic — ``site_url`` breaks
    every tie — because a list that reorders between two loads makes a user
    doubt the one they picked last time.

    Nothing is selected automatically. The flags exist to make the obvious
    choice easy to find, not to make it for them.
    """

    offered = [
        OfferedProperty(
            site_url=candidate.site_url,
            permission_level=candidate.permission_level,
            property_type=property_type_of(candidate.site_url),
            matches_project_domain=matches_project_domain(candidate.site_url, project_domain_key),
            currently_selected=candidate.site_url == selected_site_url,
        )
        for candidate in usable_properties(properties)
    ]

    offered.sort(
        key=lambda item: (
            not item.matches_project_domain,
            not item.currently_selected,
            item.site_url.lower(),
        )
    )
    return offered


def link_property(
    session: Session,
    *,
    seo_project_id: uuid.UUID,
    connection: GoogleConnection,
    site_url: str,
    available: tuple[GoogleProperty, ...],
    user_id: uuid.UUID | None,
    now: datetime | None = None,
) -> SiteAuditSearchConsoleLink:
    """Point a project at one property, after checking the account can reach it.

    ``available`` is the list Google returned moments ago, and the requested
    ``site_url`` must appear in it. The client's value is matched against that
    list rather than trusted, and ``permission_level`` is taken from the match
    rather than from the request — otherwise a caller could describe their own
    access, and the stored row would be a record of what they claimed.
    """

    moment = now or datetime.now(UTC)

    match = next(
        (candidate for candidate in usable_properties(available) if candidate.site_url == site_url),
        None,
    )
    if match is None:
        raise PropertyNotAccessible("this google account cannot reach that property")

    link = session.scalar(
        sa.select(SiteAuditSearchConsoleLink).where(
            SiteAuditSearchConsoleLink.seo_project_id == seo_project_id
        )
    )

    if link is None:
        link = SiteAuditSearchConsoleLink(
            seo_project_id=seo_project_id,
            google_connection_id=connection.id,
            site_url=match.site_url,
            property_type=property_type_of(match.site_url),
            permission_level=match.permission_level,
            connected_by_user_id=user_id,
            created_at=moment,
            updated_at=moment,
        )
        session.add(link)
    else:
        # Updated in place rather than deleted and re-inserted: UNIQUE
        # (seo_project_id) makes the delete-then-insert a window in which the
        # project has no property, and an interrupted change would leave it
        # there permanently.
        link.google_connection_id = connection.id
        link.site_url = match.site_url
        link.property_type = property_type_of(match.site_url)
        link.permission_level = match.permission_level
        link.connected_by_user_id = user_id
        link.updated_at = moment

    session.flush()
    return link


def unlink_property(session: Session, *, seo_project_id: uuid.UUID) -> bool:
    """Remove a project's property link. Returns whether there was one.

    Only the link. The ``GoogleConnection`` survives, because it is shared: an
    agency's other projects are pointed at the same account, and "stop reporting
    on this project" must not mean "sign every project out of Google".
    """

    result = cast(
        "CursorResult[Any]",
        session.execute(
            sa.delete(SiteAuditSearchConsoleLink).where(
                SiteAuditSearchConsoleLink.seo_project_id == seo_project_id
            )
        ),
    )
    return bool(result.rowcount)


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    """Property-wide totals. ``ctr``/``position`` are None when there is no data.

    Nullable rather than zero on purpose. A zero CTR is a measurement; "we have
    no measurement" is not, and a chart that cannot tell them apart draws a
    confident line through the middle of nothing.
    """

    clicks: float
    impressions: float
    ctr: float | None
    position: float | None


@dataclass(frozen=True, slots=True)
class PerformanceEntry:
    """One query or one page, with its own metrics."""

    key: str
    clicks: float
    impressions: float
    ctr: float
    position: float


@dataclass(frozen=True, slots=True)
class PerformanceReport:
    site_url: str
    start_date: date
    end_date: date
    data_state: str
    summary: PerformanceMetrics
    top_queries: list[PerformanceEntry]
    top_pages: list[PerformanceEntry]


def default_date_range(*, today: date | None = None) -> tuple[date, date]:
    """The last 28 finalized Search Console days.

    ``today`` is injectable so this is testable without freezing a clock, and it
    defaults to the Pacific date because that is the calendar Search Console
    reports on — deriving it from the server's local day would move the window
    depending on where the container runs.
    """

    reference = today or datetime.now(SEARCH_CONSOLE_TIMEZONE).date()
    end = reference - timedelta(days=FINALIZED_DATA_LAG_DAYS)
    start = end - timedelta(days=DEFAULT_LOOKBACK_DAYS - 1)
    return start, end


def validate_date_range(
    start: date | None,
    end: date | None,
    *,
    today: date | None = None,
) -> tuple[date, date]:
    """Resolve and check a requested window, or raise :class:`InvalidDateRange`.

    Either bound may be omitted and is filled from the default window. A future
    date is refused rather than clamped: silently returning a different range
    than the one asked for is how a caller ends up comparing two reports that do
    not cover the same days.
    """

    reference = today or datetime.now(SEARCH_CONSOLE_TIMEZONE).date()
    default_start, default_end = default_date_range(today=reference)

    resolved_start = start or default_start
    resolved_end = end or default_end

    if resolved_start > resolved_end:
        raise InvalidDateRange("start_date must not be after end_date")
    if resolved_end > reference:
        raise InvalidDateRange("end_date must not be in the future")
    if (resolved_end - resolved_start).days + 1 > MAX_RANGE_DAYS:
        raise InvalidDateRange(f"the requested range exceeds {MAX_RANGE_DAYS} days")

    return resolved_start, resolved_end


def clamp_row_limit(limit: int | None) -> int:
    """Row limits are bounded here as well as in the schema.

    The schema is the caller-facing guard; this is the one that still holds when
    a future internal caller skips it.
    """

    if limit is None:
        return DEFAULT_ROW_LIMIT
    return max(MIN_ROW_LIMIT, min(MAX_ROW_LIMIT, limit))


def _summary_from(rows: tuple[SearchAnalyticsRow, ...]) -> PerformanceMetrics:
    """The property-wide row, or an explicit nothing.

    Deliberately does not average the per-query rows when the summary is absent:
    those rows are a truncated top-N, so a total computed from them would be a
    plausible number that is simply wrong.
    """

    if not rows:
        return PerformanceMetrics(clicks=0.0, impressions=0.0, ctr=None, position=None)

    row = rows[0]
    if row.impressions <= 0:
        # No impressions means CTR and position are undefined rather than zero —
        # position 0 would render as "ranked first".
        return PerformanceMetrics(
            clicks=row.clicks, impressions=row.impressions, ctr=None, position=None
        )

    return PerformanceMetrics(
        clicks=row.clicks,
        impressions=row.impressions,
        ctr=row.ctr,
        position=row.position,
    )


def _entries_from(rows: tuple[SearchAnalyticsRow, ...]) -> list[PerformanceEntry]:
    return [
        PerformanceEntry(
            key=row.keys[0],
            clicks=row.clicks,
            impressions=row.impressions,
            ctr=row.ctr,
            position=row.position,
        )
        for row in rows
        if row.keys
    ]


def build_performance_report(
    *,
    provider: GoogleOAuthProvider,
    access_token: str,
    site_url: str,
    start: date,
    end: date,
    row_limit: int,
) -> PerformanceReport:
    """At most three bounded queries: the total, the top queries, the top pages.

    Three calls, no pagination, no loop. The number is fixed in the code rather
    than derived from the response, so a report cannot grow into an unbounded
    walk of a large property — the cost of this endpoint is knowable before it
    runs.
    """

    start_iso, end_iso = start.isoformat(), end.isoformat()

    summary_rows = provider.query_search_analytics(
        access_token=access_token,
        site_url=site_url,
        start_date=start_iso,
        end_date=end_iso,
        dimensions=(),
        row_limit=1,
    )
    query_rows = provider.query_search_analytics(
        access_token=access_token,
        site_url=site_url,
        start_date=start_iso,
        end_date=end_iso,
        dimensions=("query",),
        row_limit=row_limit,
    )
    page_rows = provider.query_search_analytics(
        access_token=access_token,
        site_url=site_url,
        start_date=start_iso,
        end_date=end_iso,
        dimensions=("page",),
        row_limit=row_limit,
    )

    summary = _summary_from(summary_rows)
    top_queries = _entries_from(query_rows)
    top_pages = _entries_from(page_rows)

    has_data = bool(summary_rows) and summary.impressions > 0
    return PerformanceReport(
        site_url=site_url,
        start_date=start,
        end_date=end,
        data_state="ok" if has_data else "no_data",
        summary=summary,
        top_queries=top_queries,
        top_pages=top_pages,
    )


__all__ = [
    "ClaimedState",
    "GoogleIdentityError",
    "GoogleOAuthError",
    "InvalidDateRange",
    "MissingRefreshToken",
    "NoPropertySelected",
    "OAuthStateExpired",
    "OAuthStateInvalid",
    "OfferedProperty",
    "PerformanceEntry",
    "PerformanceMetrics",
    "PerformanceReport",
    "PropertyNotAccessible",
    "ReauthRequired",
    "StartedAuthorization",
    "build_performance_report",
    "canonical_scopes",
    "clamp_row_limit",
    "code_challenge_for",
    "consume_oauth_state",
    "default_date_range",
    "get_access_token",
    "get_org_connection",
    "get_project_link",
    "hash_oauth_value",
    "link_property",
    "list_org_connections",
    "offer_properties",
    "purge_expired_states",
    "start_authorization",
    "unlink_property",
    "upsert_google_connection",
    "usable_properties",
    "validate_date_range",
    "verify_identity_for_state",
]
