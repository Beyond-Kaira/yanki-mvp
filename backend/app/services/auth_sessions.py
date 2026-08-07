"""Refresh-session persistence, rotation, and revocation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import AuthSession
from app.services.tokens import (
    IssuedToken,
    TokenClaims,
    TokenType,
    TokenValidationError,
    calculate_refresh_family_expiry,
    decode_token,
    hash_refresh_jti,
    issue_access_token,
    issue_refresh_token,
)


@dataclass(frozen=True, slots=True)
class SessionTokens:
    """Access and refresh tokens issued for one authenticated session."""

    access_token: IssuedToken
    refresh_token: IssuedToken
    family_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class SessionSummary:
    """One active sign-in, as its owner sees it in "your devices".

    A *session* here is a whole refresh-token family — one login on one device —
    not a single rotation generation. Rotation replaces the live row many times
    over the life of a session, so exposing rows would show a person dozens of
    entries for one browser. The family is collapsed to a single line.

    ``id`` is the family id. It names a session for revocation and nothing more:
    it is not the ``refresh_jti_hash`` and cannot be replayed to authenticate.
    """

    id: uuid.UUID
    created_at: datetime
    last_active_at: datetime
    expires_at: datetime
    current: bool


class RefreshSessionError(ValueError):
    """Base error for an unusable refresh session."""


class InvalidRefreshSessionError(RefreshSessionError):
    """Raised when a refresh token has no usable persisted session."""


class RefreshTokenReuseDetectedError(RefreshSessionError):
    """Raised after reuse of a consumed token revokes its whole family."""


def start_refresh_session(
    session: Session,
    *,
    user_id: uuid.UUID,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> SessionTokens:
    """Start a new refresh-token family after successful authentication."""

    resolved_settings = settings or get_settings()
    issued_at = _resolve_now(now)
    family_id = uuid.uuid4()

    family_expires_at = calculate_refresh_family_expiry(
        settings=resolved_settings,
        now=issued_at,
    )
    access_token = issue_access_token(
        user_id,
        settings=resolved_settings,
        now=issued_at,
    )
    refresh_token = issue_refresh_token(
        user_id,
        expires_at=family_expires_at,
        settings=resolved_settings,
        now=issued_at,
    )

    auth_session = AuthSession(
        user_id=user_id,
        family_id=family_id,
        refresh_jti_hash=hash_refresh_jti(
            refresh_token.jti,
            settings=resolved_settings,
        ),
        expires_at=family_expires_at,
    )

    try:
        session.add(auth_session)
        session.commit()
    except Exception:
        session.rollback()
        raise

    return SessionTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        family_id=family_id,
    )


def rotate_refresh_session(
    session: Session,
    *,
    refresh_token: str,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> SessionTokens:
    """Consume one refresh token and atomically issue its successor."""

    resolved_settings = settings or get_settings()
    claims = _decode_refresh_token(
        refresh_token,
        settings=resolved_settings,
    )
    rotation_time = _resolve_now(now)
    refresh_jti_hash = hash_refresh_jti(
        claims.jti,
        settings=resolved_settings,
    )

    try:
        current_session = _lock_refresh_family(
            session,
            refresh_jti_hash=refresh_jti_hash,
        )

        if current_session is None or current_session.user_id != claims.user_id:
            raise InvalidRefreshSessionError("invalid refresh session")

        if current_session.revoked_at is not None:
            raise InvalidRefreshSessionError("refresh session is revoked")

        family_expires_at = _database_datetime_as_utc(
            current_session.expires_at,
        )

        if family_expires_at <= rotation_time:
            raise InvalidRefreshSessionError("refresh session is expired")

        if current_session.consumed_at is not None or current_session.replaced_by_id is not None:
            _revoke_family(
                session,
                family_id=current_session.family_id,
                revoked_at=rotation_time,
            )
            session.commit()

            raise RefreshTokenReuseDetectedError(
                "refresh token reuse detected",
            )

        access_token = issue_access_token(
            current_session.user_id,
            settings=resolved_settings,
            now=rotation_time,
        )
        next_refresh_token = issue_refresh_token(
            current_session.user_id,
            expires_at=family_expires_at,
            settings=resolved_settings,
            now=rotation_time,
        )

        successor = AuthSession(
            user_id=current_session.user_id,
            family_id=current_session.family_id,
            refresh_jti_hash=hash_refresh_jti(
                next_refresh_token.jti,
                settings=resolved_settings,
            ),
            expires_at=family_expires_at,
        )

        session.add(successor)
        session.flush()

        current_session.consumed_at = rotation_time
        current_session.replaced_by_id = successor.id

        session.commit()

        return SessionTokens(
            access_token=access_token,
            refresh_token=next_refresh_token,
            family_id=current_session.family_id,
        )
    except RefreshTokenReuseDetectedError:
        # The family revocation was deliberately committed before this error.
        raise
    except Exception:
        session.rollback()
        raise


def revoke_refresh_session_family(
    session: Session,
    *,
    refresh_token: str,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> bool:
    """Revoke the family represented by a refresh token.

    Invalid, unknown, or expired tokens are treated as an idempotent no-op so
    logout does not disclose whether a supplied token was previously valid.
    """

    resolved_settings = settings or get_settings()

    try:
        claims = decode_token(
            refresh_token,
            expected_type=TokenType.REFRESH,
            settings=resolved_settings,
        )
    except TokenValidationError:
        return False

    revoked_at = _resolve_now(now)
    refresh_jti_hash = hash_refresh_jti(
        claims.jti,
        settings=resolved_settings,
    )

    try:
        current_session = _lock_refresh_family(
            session,
            refresh_jti_hash=refresh_jti_hash,
        )

        if current_session is None or current_session.user_id != claims.user_id:
            session.rollback()
            return False

        _revoke_family(
            session,
            family_id=current_session.family_id,
            revoked_at=revoked_at,
        )
        session.commit()

        return True
    except Exception:
        session.rollback()
        raise


def _decode_refresh_token(
    token: str,
    *,
    settings: Settings,
) -> TokenClaims:
    try:
        return decode_token(
            token,
            expected_type=TokenType.REFRESH,
            settings=settings,
        )
    except TokenValidationError as exc:
        raise InvalidRefreshSessionError(
            "invalid refresh token",
        ) from exc


def _lock_refresh_family(
    session: Session,
    *,
    refresh_jti_hash: str,
) -> AuthSession | None:
    # The first lookup discovers the family. The second query locks every row in
    # that family in a stable order so rotation, reuse detection, and logout for
    # one device/session cannot modify the family concurrently.
    target = session.scalar(
        select(AuthSession)
        .where(
            AuthSession.refresh_jti_hash == refresh_jti_hash,
        )
        .execution_options(populate_existing=True),
    )

    if target is None:
        return None

    family_rows = session.scalars(
        select(AuthSession)
        .where(
            AuthSession.family_id == target.family_id,
        )
        .order_by(AuthSession.id)
        .with_for_update()
        .execution_options(populate_existing=True),
    ).all()

    return next(
        (family_row for family_row in family_rows if family_row.id == target.id),
        None,
    )


def revoke_all_sessions_for_user(
    session: Session,
    *,
    user_id: uuid.UUID,
    now: datetime | None = None,
) -> int:
    """Revoke every live refresh session this user holds, on every device.

    What an administrator means by "disable this account" is *stop them*, and
    an account that keeps working until its refresh token happens to expire is
    not disabled — it is scheduled for disablement, which is a different and
    much weaker promise. So disabling calls this.

    It closes the slow half of the problem. The fast half is the access token,
    which is a self-contained JWT this service cannot recall; that is handled
    at the other end, where ``get_current_user`` refuses a non-active user on
    every request.

    Does not commit — the caller owns the transaction, because revoking the
    sessions of an account whose disablement then rolls back would sign someone
    out of a change that never happened. Returns the number of rows revoked, so
    the caller can record it.
    """

    revoked_at = _resolve_now(now)
    # Counted before the UPDATE rather than read from `rowcount`: the ORM's
    # `Result` does not expose it in a typed way, and the count is only ever
    # used as audit detail — an approximate number in a log is worse than one
    # read from the same transaction that performs the write.
    live = session.scalars(
        select(AuthSession.id).where(
            AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)
        )
    ).all()
    if not live:
        return 0

    session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=revoked_at),
        execution_options={"synchronize_session": "fetch"},
    )
    return len(live)


def list_active_sessions_for_user(
    session: Session,
    *,
    user_id: uuid.UUID,
    current_family_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> list[SessionSummary]:
    """Every live session this user holds, most-recently-used first.

    One entry per family (per device/login), collapsed from its rotation rows.
    A family is *live* when its tip — the one unconsumed row — is neither revoked
    nor expired; a family whose tip is revoked (logout, another device's
    "sign out everywhere", or reuse detection) or past its expiry is dropped, so
    the list mirrors what could actually be used to obtain a new access token.

    Never reads or returns ``refresh_jti_hash``. The only identifier that leaves
    here is the family id, which cannot be replayed as a credential.
    """

    moment = _resolve_now(now)

    rows = session.scalars(
        select(AuthSession)
        .where(AuthSession.user_id == user_id)
        .order_by(AuthSession.family_id, AuthSession.created_at)
    ).all()

    families: dict[uuid.UUID, list[AuthSession]] = {}
    for row in rows:
        families.setdefault(row.family_id, []).append(row)

    summaries: list[SessionSummary] = []
    for family_id, family_rows in families.items():
        # The tip is the single row that has not been consumed by a rotation.
        # Revocation sets ``revoked_at`` on every row but leaves the tip
        # unconsumed, so the tip is still where liveness is decided.
        tip = next((row for row in family_rows if row.consumed_at is None), None)
        if tip is None:
            continue
        if tip.revoked_at is not None:
            continue
        if _database_datetime_as_utc(tip.expires_at) <= moment:
            continue

        created_at = min(_database_datetime_as_utc(row.created_at) for row in family_rows)
        last_active_at = max(_database_datetime_as_utc(row.created_at) for row in family_rows)
        summaries.append(
            SessionSummary(
                id=family_id,
                created_at=created_at,
                last_active_at=last_active_at,
                expires_at=_database_datetime_as_utc(tip.expires_at),
                current=current_family_id is not None and family_id == current_family_id,
            )
        )

    summaries.sort(key=lambda summary: summary.last_active_at, reverse=True)
    return summaries


def revoke_session_family_for_user(
    session: Session,
    *,
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    now: datetime | None = None,
) -> bool:
    """Revoke one session (family), but only if it belongs to this user.

    Returns ``False`` — not raising, and not distinguishing the cases — when the
    family is not the caller's, whether because it is someone else's or does not
    exist. The route turns that single answer into a 404, so a caller cannot
    probe for the existence of another user's session ids.

    Does **not** commit: the caller owns the transaction so the revocation and
    its audit event land together, the same contract
    :func:`revoke_all_sessions_for_user` keeps.
    """

    revoked_at = _resolve_now(now)

    owned = session.scalar(
        select(AuthSession.id)
        .where(AuthSession.family_id == family_id, AuthSession.user_id == user_id)
        .limit(1)
    )
    if owned is None:
        return False

    _revoke_family(session, family_id=family_id, revoked_at=revoked_at)
    return True


def revoke_other_sessions_for_user(
    session: Session,
    *,
    user_id: uuid.UUID,
    keep_family_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> int:
    """Revoke every live session this user holds except ``keep_family_id``.

    This is "sign out everywhere else". Keeping the current family alive is a
    deliberate choice: the action is reached from a signed-in device, and ending
    that device's own session as a side effect would sign the person out of the
    click they just made, with no chance to see it worked. "Log out" already
    exists for ending the current session on purpose.

    With ``keep_family_id=None`` it spares nothing and becomes a true
    everywhere-including-here revoke. Does not commit; returns the number of rows
    revoked so the caller can record it.
    """

    revoked_at = _resolve_now(now)

    conditions = [AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)]
    if keep_family_id is not None:
        conditions.append(AuthSession.family_id != keep_family_id)

    live = session.scalars(select(AuthSession.id).where(*conditions)).all()
    if not live:
        return 0

    session.execute(
        update(AuthSession).where(*conditions).values(revoked_at=revoked_at),
        execution_options={"synchronize_session": "fetch"},
    )
    return len(live)


def _revoke_family(
    session: Session,
    *,
    family_id: uuid.UUID,
    revoked_at: datetime,
) -> None:
    statement = (
        update(AuthSession)
        .where(
            AuthSession.family_id == family_id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=revoked_at)
    )

    session.execute(
        statement,
        execution_options={"synchronize_session": "fetch"},
    )


def _resolve_now(value: datetime | None) -> datetime:
    resolved = value or datetime.now(UTC)

    if resolved.tzinfo is None or resolved.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    return resolved.astimezone(UTC).replace(microsecond=0)


def _database_datetime_as_utc(value: datetime) -> datetime:
    # PostgreSQL returns timezone-aware values. SQLite drops timezone metadata,
    # so hermetic SQLite tests treat a naive stored value as UTC.
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)
