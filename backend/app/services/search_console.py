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
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy import CursorResult
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import GoogleConnection, GoogleOAuthState
from app.gsc.base import (
    GoogleIdentity,
    GoogleIdentityError,
    GoogleOAuthError,
    GoogleOAuthProvider,
    GoogleTokens,
)
from app.services.token_crypto import encrypt_secret

# 32 bytes of entropy each, url-safe. The state and nonce travel in a URL and
# the verifier must be 43-128 characters per RFC 7636; token_urlsafe(32) yields
# 43, the minimum that satisfies it.
_ENTROPY_BYTES = 32


class SearchConsoleError(RuntimeError):
    """Base for failures the router turns into a specific outcome."""


class OAuthStateInvalid(SearchConsoleError):
    """No live state matched — unknown, already consumed, or never existed."""


class OAuthStateExpired(SearchConsoleError):
    """The state existed and its window had closed."""


class MissingRefreshToken(SearchConsoleError):
    """Google returned no refresh token and none is already stored."""


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


__all__ = [
    "ClaimedState",
    "GoogleIdentityError",
    "GoogleOAuthError",
    "MissingRefreshToken",
    "OAuthStateExpired",
    "OAuthStateInvalid",
    "StartedAuthorization",
    "canonical_scopes",
    "code_challenge_for",
    "consume_oauth_state",
    "hash_oauth_value",
    "purge_expired_states",
    "start_authorization",
    "upsert_google_connection",
    "verify_identity_for_state",
]
