"""Invitations — the only way to join an organization you did not create (P7.4).

An invitation grants a role to someone who may not have an account yet, which
makes it a credential with a blast radius, and shapes every decision here.

**The token is never stored.** :func:`mint_token` returns the plaintext exactly
once, to the caller, which puts it in one email; the row keeps only a SHA-256.
A leaked database therefore leaks the *existence* of invitations, not a set of
working ones. This mirrors ``auth_sessions``' treatment of refresh tokens, on
purpose — one discipline for tokens across the codebase is easier to keep than
two.

**Every failure is one shape.** :func:`redeem` answers with a
:class:`InvitationProblem` naming which of *unknown / expired / revoked /
already accepted* applied, and the routes turn all of them into the same 404 for
an unauthenticated caller. Distinguishing them at the edge would let anyone with
a token guess whether it was ever valid; keeping the distinction *inside* the
service is what lets the accept screen say something specific to a person who
holds a real, expired token.

**Accepting is one transaction.** The user, their membership and the state
change on the invitation land together, because a half-accepted invitation is
either an account that belongs to no org (unusable) or a consumed token that
granted nothing (unrecoverable without support).

**Roles are checked against the assignable set, not trusted.** The platform
roles are excluded there, so no invitation can mint Yanki staff — the exact
privilege-escalation this table would otherwise open.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Invitation, Membership, Organization, User

# Long enough that guessing is hopeless (256 bits of entropy), URL-safe so it
# survives an email client's linkifier without escaping.
TOKEN_BYTES = 32

# Fourteen days. Long enough to survive a holiday, short enough that a forgotten
# invitation in an abandoned inbox is not an indefinite standing grant.
DEFAULT_TTL = timedelta(days=14)

# Statuses. Expiry is deliberately absent — it is derived from `expires_at`, so
# it cannot go stale between sweeps. See the model docstring.
PENDING = "pending"
ACCEPTED = "accepted"
REVOKED = "revoked"


class InvitationProblem(StrEnum):
    """Why an invitation cannot be used. Never shown verbatim to a stranger."""

    UNKNOWN = "unknown"
    EXPIRED = "expired"
    REVOKED = "revoked"
    ALREADY_ACCEPTED = "already_accepted"
    ORG_INACTIVE = "org_inactive"
    EMAIL_TAKEN = "email_taken"
    ALREADY_MEMBER = "already_member"


class InvitationError(RuntimeError):
    """Raised when an invitation cannot be created or redeemed."""

    def __init__(self, problem: InvitationProblem, message: str | None = None) -> None:
        super().__init__(message or problem.value)
        self.problem = problem


@dataclass(frozen=True)
class MintedInvitation:
    """A stored invitation and the one copy of its token that will ever exist."""

    invitation: Invitation
    token: str


def mint_token() -> str:
    """A fresh, URL-safe invitation token."""

    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """The stored form of a token.

    Plain SHA-256, not a password hash. The trade is deliberate and it is the
    same one ``auth_sessions`` makes: this value has 256 bits of entropy from a
    CSPRNG, so there is nothing for a slow hash to defend against, and the lookup
    happens on every accept request where an Argon2 verify per candidate row
    would be a denial-of-service surface.
    """

    return hashlib.sha256(token.encode()).hexdigest()


def is_expired(invitation: Invitation, *, now: datetime | None = None) -> bool:
    """Has this invitation aged out?

    Normalizes a naive ``expires_at`` to UTC first: SQLite returns naive
    datetimes where Postgres returns aware ones, and comparing the two raises.
    A crash here would read as "invalid invitation", which is the wrong answer
    given by the wrong mechanism.
    """

    moment = now or datetime.now(UTC)
    expires = invitation.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires <= moment


def problem_for(invitation: Invitation, *, now: datetime | None = None) -> InvitationProblem | None:
    """Why this invitation cannot be redeemed, or ``None`` if it can.

    Order matters: revoked beats expired, because an administrator who revoked
    an invitation wants that recorded as the reason it failed even if it would
    have lapsed anyway.
    """

    if invitation.status == REVOKED:
        return InvitationProblem.REVOKED
    if invitation.status == ACCEPTED:
        return InvitationProblem.ALREADY_ACCEPTED
    if is_expired(invitation, now=now):
        return InvitationProblem.EXPIRED
    return None


def find_by_token(session: Session, token: str, *, lock: bool = False) -> Invitation | None:
    """The invitation a token names, whatever state it is in.

    Returns rows that are expired, revoked or spent as well as usable ones —
    the caller decides what to say about them, because "this invitation expired
    last week" is a much better message than "not found" for someone holding a
    genuine link, and only the caller knows whether it is safe to say it.

    ``lock=True`` takes a row lock, and the **accept** path uses it while the
    **preview** path does not. Two simultaneous accepts of one link would
    otherwise both read ``pending``, both pass :func:`problem_for`, and both
    proceed — single-use enforced by a check that two callers can pass at once
    is not single-use. Today they are backstopped by the unique constraint on
    ``users.email``, so the second one loses with a 409 rather than creating a
    second account; that is safety by accident of another table's constraint,
    and it would evaporate the moment an already-registered user accepts (where
    no insert happens at all). Locking makes it safety by design.

    The preview must NOT lock: it is unauthenticated, and a lock there would
    let anyone holding a token pin a row for the length of a request.
    """

    if not token:
        return None
    statement = select(Invitation).where(Invitation.token_hash == hash_token(token))
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def list_invitations(
    session: Session,
    *,
    org_id: uuid.UUID,
    status: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[Invitation]]:
    """A page of the org's invitations, newest first, with the matching total."""

    base = select(Invitation).where(Invitation.org_id == org_id)
    if status:
        base = base.where(Invitation.status == status)
    if q:
        needle = f"%{q.strip().lower()}%"
        base = base.where(or_(func.lower(Invitation.email).like(needle)))

    total = int(session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = list(
        session.scalars(base.order_by(Invitation.created_at.desc()).limit(limit).offset(offset))
    )
    return total, rows


def existing_pending(session: Session, *, org_id: uuid.UUID, email: str) -> Invitation | None:
    """A live invitation to this address in this org, if there is one."""

    return session.scalar(
        select(Invitation).where(
            Invitation.org_id == org_id,
            Invitation.email == email,
            Invitation.status == PENDING,
        )
    )


def is_member(session: Session, *, org_id: uuid.UUID, email: str) -> bool:
    """Does this address already hold an ACTIVE seat in this org?

    Deactivated memberships deliberately do not count. Re-inviting someone who
    was removed from the team is a normal thing to do — a contractor coming
    back, a colleague returning from leave — and refusing it would leave no way
    to restore them except a database edit. :func:`redeem` reactivates the
    existing row rather than inserting a second one.
    """

    return (
        session.scalar(
            select(Membership.id)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.org_id == org_id,
                User.email == email,
                Membership.status == "active",
            )
            .limit(1)
        )
        is not None
    )


def create_invitation(
    session: Session,
    *,
    org_id: uuid.UUID,
    email: str,
    role: str,
    invited_by_user_id: uuid.UUID | None,
    workspace_id: uuid.UUID | None = None,
    ttl: timedelta = DEFAULT_TTL,
    now: datetime | None = None,
) -> MintedInvitation:
    """Create a pending invitation and return it with its one-time token.

    Refuses an address that already holds a seat in this org (:class:`
    InvitationProblem.ALREADY_MEMBER`) — inviting an existing member is almost
    always an attempt to change their role, and doing it through this path would
    mint a token that can only ever fail at accept time.

    A **live invitation to the same address is replaced, not duplicated**: the
    old one is revoked and a new token is minted. That is what "resend" means to
    the person clicking it, it keeps the partial unique index satisfied, and it
    guarantees at most one working link per invitee at any moment.
    """

    moment = now or datetime.now(UTC)
    email = email.strip().lower()

    if is_member(session, org_id=org_id, email=email):
        raise InvitationError(
            InvitationProblem.ALREADY_MEMBER,
            "that person is already a member of this organization",
        )

    superseded = existing_pending(session, org_id=org_id, email=email)
    previous_sends = 0
    if superseded is not None:
        superseded.status = REVOKED
        superseded.revoked_at = moment
        previous_sends = superseded.sent_count
        session.flush()

    token = mint_token()
    invitation = Invitation(
        org_id=org_id,
        workspace_id=workspace_id,
        email=email,
        role=role,
        token_hash=hash_token(token),
        invited_by_user_id=invited_by_user_id,
        status=PENDING,
        expires_at=moment + ttl,
        sent_count=previous_sends + 1,
        last_sent_at=moment,
    )
    session.add(invitation)
    session.flush()
    return MintedInvitation(invitation=invitation, token=token)


def revoke_invitation(
    session: Session, invitation: Invitation, *, now: datetime | None = None
) -> Invitation:
    """Withdraw a pending invitation. Idempotent for an already-revoked one.

    An **accepted** invitation is not revocable: the seat exists, and taking it
    back is a membership change, not a token change. Saying so here rather than
    quietly succeeding is what stops an administrator believing they removed
    someone's access when they did not.
    """

    if invitation.status == ACCEPTED:
        raise InvitationError(
            InvitationProblem.ALREADY_ACCEPTED,
            "that invitation was already accepted — remove the member instead",
        )
    if invitation.status == PENDING:
        invitation.status = REVOKED
        invitation.revoked_at = now or datetime.now(UTC)
        session.flush()
    return invitation


def resend_invitation(
    session: Session,
    invitation: Invitation,
    *,
    ttl: timedelta = DEFAULT_TTL,
    now: datetime | None = None,
) -> MintedInvitation:
    """Mint a fresh token for an existing invitation and extend its expiry.

    The old token stops working immediately, which is the property that makes
    resending safe to offer freely: a link forwarded to the wrong person is
    fixed by pressing resend, not by a support ticket.

    Works on an expired invitation as well as a live one — that is the common
    case, and forcing the administrator to delete and re-create it would lose
    who originally invited whom.
    """

    moment = now or datetime.now(UTC)
    if invitation.status == ACCEPTED:
        raise InvitationError(
            InvitationProblem.ALREADY_ACCEPTED,
            "that invitation was already accepted",
        )

    token = mint_token()
    invitation.token_hash = hash_token(token)
    invitation.status = PENDING
    invitation.revoked_at = None
    invitation.expires_at = moment + ttl
    invitation.sent_count = invitation.sent_count + 1
    invitation.last_sent_at = moment
    session.flush()
    return MintedInvitation(invitation=invitation, token=token)


@dataclass(frozen=True)
class RedeemedInvitation:
    """What accepting produced: the invitation, the user, and their membership."""

    invitation: Invitation
    user: User
    membership: Membership
    created_user: bool


def redeem(
    session: Session,
    *,
    invitation: Invitation,
    user: User,
    now: datetime | None = None,
) -> RedeemedInvitation:
    """Consume an invitation, seating ``user`` in its organization.

    Assumes the caller has already checked :func:`problem_for` — this function
    is the state change, and splitting the check from the change keeps the
    "what should we tell them" decision in the route where the audience is known.

    Does not commit: the caller owns the transaction, because creating the user
    and consuming the invitation must be atomic.

    Re-seating an existing membership row (a previously deactivated member being
    re-invited) reactivates it and applies the invited role, rather than
    inserting a second membership the unique constraint would refuse.
    """

    moment = now or datetime.now(UTC)

    membership = session.scalar(
        select(Membership).where(
            Membership.org_id == invitation.org_id, Membership.user_id == user.id
        )
    )
    if membership is None:
        membership = Membership(
            org_id=invitation.org_id,
            user_id=user.id,
            role=invitation.role,
            status="active",
        )
        session.add(membership)
    else:
        membership.role = invitation.role
        membership.status = "active"

    invitation.status = ACCEPTED
    invitation.accepted_at = moment
    invitation.accepted_user_id = user.id
    session.flush()

    return RedeemedInvitation(
        invitation=invitation,
        user=user,
        membership=membership,
        created_user=False,
    )


def organization_is_open(session: Session, org_id: uuid.UUID) -> bool:
    """Can anyone still join this organization?

    A suspended or closed org must not accept new members even through a token
    minted while it was healthy — otherwise suspension is advisory.
    """

    status = session.scalar(select(Organization.status).where(Organization.id == org_id))
    return status in {"active", "trial"}
