"""The public half of the invitation flow: preview a link, then accept it.

Unauthenticated by necessity — the whole point is that the person holding the
link does not have an account yet — which makes this the most exposed surface
the Admin Panel owns. Four decisions follow from that.

**The token is the only credential, and it is never in a body.** It arrives in
the path, is hashed before it touches the database, and no response ever echoes
it back.

**Failures are specific, deliberately.** Elsewhere in this codebase an unknown
resource and a forbidden one answer identically, because distinguishing them
lets someone enumerate. That reasoning does not apply here: a 256-bit token is
not enumerable, so anyone holding one is the intended recipient, and telling
them "this expired on Tuesday" is both safe and the difference between a
recoverable moment and an inexplicable dead end. An *unknown* token still gets a
flat 404.

**Acceptance is idempotent in outcome, not in effect.** A token is single-use:
the second POST finds it accepted and says so, rather than creating a second
account.

**The invited address is authoritative.** The account is created with the email
the invitation names, never one supplied by the caller — otherwise an invitation
to alice@ would be a way to create an account as bob@ with alice's granted role.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth_cookies import set_refresh_cookie
from app.api.auth_dependencies import get_optional_user
from app.api.schemas import (
    InvitationAcceptRequest,
    InvitationPreviewOut,
    LoginResponse,
    UserOut,
)
from app.config import Settings, get_settings
from app.db.models import Invitation, Organization, User
from app.db.session import get_session
from app.services import audit, invitations
from app.services.auth import get_user_by_email, hash_password
from app.services.auth_sessions import start_refresh_session
from app.services.tenancy import OrgContext
from app.services.tokens import TokenConfigurationError

router = APIRouter(prefix="/api/v1/invitations", tags=["invitations"])

# Token length is bounded in the path so a multi-megabyte "token" is rejected by
# the framework before it reaches a hash function or a query.
TokenPath = Annotated[str, Path(min_length=16, max_length=256)]

# What each unusable state says, and with which status. 410 Gone rather than 404
# for all three: the link WAS valid, which is exactly what the person needs to
# know, and it distinguishes "you waited too long" from "this was never real".
_PROBLEM_RESPONSES = {
    invitations.InvitationProblem.EXPIRED: (
        status.HTTP_410_GONE,
        "This invitation has expired. Ask whoever invited you to send a new one.",
    ),
    invitations.InvitationProblem.REVOKED: (
        status.HTTP_410_GONE,
        "This invitation was withdrawn. Ask whoever invited you to send a new one.",
    ),
    invitations.InvitationProblem.ALREADY_ACCEPTED: (
        status.HTTP_410_GONE,
        "This invitation has already been used. Sign in with the account you created.",
    ),
    invitations.InvitationProblem.ORG_INACTIVE: (
        status.HTTP_410_GONE,
        "That organization is not accepting new members right now.",
    ),
}

_NOT_FOUND = "That invitation link is not valid."


def _usable_or_error(session: Session, token: str, *, lock: bool = False) -> Invitation:
    """The invitation this token names, or the right HTTP error explaining why not.

    ``lock`` is passed by the accept path and not by the preview — see
    :func:`app.services.invitations.find_by_token` for why the asymmetry is
    deliberate rather than an oversight.
    """

    invitation = invitations.find_by_token(session, token, lock=lock)
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)

    problem = invitations.problem_for(invitation)
    if problem is None and not invitations.organization_is_open(session, invitation.org_id):
        problem = invitations.InvitationProblem.ORG_INACTIVE

    if problem is not None:
        code, message = _PROBLEM_RESPONSES[problem]
        raise HTTPException(status_code=code, detail=message)

    return invitation


@router.get("/{token}", response_model=InvitationPreviewOut)
def preview_invitation(
    token: TokenPath,
    session: Annotated[Session, Depends(get_session)],
) -> InvitationPreviewOut:
    """What this link is for, so the accept screen can say what is being joined.

    Read-only and side-effect free: opening the link must not consume it, or an
    email client's link prefetcher would burn the invitation before the invitee
    ever saw it.
    """

    invitation = _usable_or_error(session, token)
    organization = session.get(Organization, invitation.org_id)

    return InvitationPreviewOut(
        email=invitation.email,
        role=invitation.role,
        organization_name=organization.name if organization is not None else "a Yanki organization",
        expires_at=invitation.expires_at,
    )


@router.post("/{token}/accept", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def accept_invitation(
    token: TokenPath,
    payload: InvitationAcceptRequest,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    current_user: Annotated[User | None, Depends(get_optional_user)] = None,
) -> LoginResponse:
    """Take the seat: create the account if needed, then join the organization.

    Three callers reach this, and each gets the only sensible answer:

    * **Nobody signed in, no account for the invited address** — the normal
      path. The account is created with the supplied password and the invited
      address, seated in the org with the invited role, and signed in.
    * **Signed in as the invited address** — seated directly; the password in
      the body is ignored rather than used to silently change their existing
      one, which would be a password reset disguised as an invitation.
    * **An account already exists for the address but nobody is signed in** —
      409 telling them to sign in first. Accepting with a *new* password here
      would be an account takeover by anyone who intercepted the link.

    All of it in one transaction: a consumed invitation that granted nothing is
    unrecoverable without support.
    """

    # Locked: two simultaneous accepts of one link must not both proceed.
    invitation = _usable_or_error(session, token, lock=True)

    existing = get_user_by_email(session, invitation.email)
    signed_in_as_invitee = current_user is not None and current_user.email == invitation.email

    if existing is not None and not signed_in_as_invitee:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "An account already exists for this address. "
                "Sign in first, then open the invitation link again."
            ),
        )

    created_user = False
    if existing is None:
        user = User(email=invitation.email, password_hash=hash_password(payload.password))
        session.add(user)
        try:
            session.flush()
        except IntegrityError as exc:
            # The race between the lookup above and this insert: another request
            # registered the same address in between.
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account already exists for this address. Sign in first.",
            ) from exc
        created_user = True
    else:
        user = existing

    redeemed = invitations.redeem(session, invitation=invitation, user=user)

    audit.emit(
        session,
        action="invitation:accept",
        context=OrgContext(
            org_id=invitation.org_id, user_id=user.id, role=redeemed.membership.role
        ),
        actor_type="user",
        actor_id=user.id,
        actor_label=user.email,
        entity_type="invitation",
        entity_id=invitation.id,
        after={
            "email": user.email,
            "role": redeemed.membership.role,
            "org_id": str(invitation.org_id),
            "created_user": created_user,
        },
    )

    try:
        tokens = start_refresh_session(session, user_id=user.id, settings=settings)
    except TokenConfigurationError as exc:
        # The seat is granted either way — rolling it back because this
        # deployment has no JWT key would throw away the accepted invitation
        # too, and the token cannot be replayed. Commit, then say sign-in is
        # unavailable.
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication unavailable",
        ) from exc

    session.commit()
    session.refresh(user)

    set_refresh_cookie(response, token=tokens.refresh_token, settings=settings)
    return LoginResponse(
        user=UserOut.model_validate(user),
        access_token=tokens.access_token.value,
    )
