"""The Admin Panel's API: who is in this organization, what they may do, and
what everybody did.

Scoped to the caller's organization, not the platform. An Organization Owner
managing their own members and a Yanki Super Admin managing every tenant are
different surfaces with different blast radii, and conflating them is how an
"admin panel" quietly becomes a way for a customer to read other customers'
data. This module is the first one; the platform back office is P7.7.

Three rules hold throughout:

* **Every read is org-scoped at the query**, not filtered in the response. A
  user outside the caller's organization is a 404, indistinguishable from one
  that does not exist, so the endpoint cannot be used to enumerate accounts.
* **Every route names the permission it needs.** ``requires()`` denies by
  default and audits the refusal, so a route added without a permission fails
  closed rather than opening a hole.
* **Every mutation is audited with before/after.** Role changes and account
  suspensions are exactly the events an operator needs to reconstruct later.

Two invariants get their own guards, because both are ways an organization can
lock itself out permanently: the last owner cannot be demoted or disabled, and
nobody can change their own role.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.org_dependencies import requires
from app.api.schemas import (
    AdminInvitationCreatedOut,
    AdminInvitationCreateRequest,
    AdminInvitationListOut,
    AdminInvitationOut,
    AdminMemberOut,
    AdminMemberUpdateRequest,
    AdminOrganizationOut,
    AdminUserListOut,
    AuditEventListOut,
    AuditEventOut,
    AuditIntegrityOut,
)
from app.config import Settings, get_settings
from app.db.models import AuditEvent, Invitation, Membership, Organization, User
from app.db.session import get_session
from app.services import audit, invitations
from app.services.auth_sessions import revoke_all_sessions_for_user
from app.services.emailer import send_invitation_email
from app.services.permissions import (
    ALL_ROLES,
    AUDIT_READ,
    MEMBER_INVITE,
    MEMBER_READ,
    MEMBER_REMOVE,
    MEMBER_ROLE_CHANGE,
    ORG_READ,
    OWNER,
    PLATFORM_ROLES,
    permissions_for,
)
from app.services.tenancy import OrgContext

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# Roles an org administrator may assign. Platform roles are excluded on purpose:
# they are Yanki staff, and a customer must not be able to grant them.
ASSIGNABLE_ROLES = sorted(ALL_ROLES - PLATFORM_ROLES)


def assignable_by(role: str | None) -> list[str]:
    """The roles this caller may grant: only ones no more powerful than their own.

    Excluding the platform roles is not sufficient on its own, and the gap it
    left was real. ``member:invite`` is held by **Manager**, and the assignable
    list contained ``owner`` — so a Manager could invite somebody as Owner and
    then be administered by the account they had just created. A Manager cannot
    *promote* anyone to Owner (that needs ``member:role_change``), so the
    invitation path was a way around the very check that guards promotion.

    The rule implemented here is the general form rather than a special case for
    Owner: **you cannot grant what you do not hold.** A role is offerable only if
    its permission set is a subset of the caller's own. That composes with roles
    added later without anybody remembering to update a list — and it has one
    consequence worth stating, because it looks like a bug and is not: an Admin
    cannot appoint a Billing Admin, since ``billing:manage`` is exactly the
    permission an Admin is denied. Buying things stays with the Owner, including
    the power to delegate buying things.
    """

    held = permissions_for(role)
    return [candidate for candidate in ASSIGNABLE_ROLES if permissions_for(candidate) <= held]


def _member_out(user: User, membership: Membership) -> AdminMemberOut:
    return AdminMemberOut(
        id=user.id,
        email=user.email,
        status=user.status,
        created_at=user.created_at,
        last_active_at=user.last_active_at,
        role=membership.role,
        membership_status=membership.status,
        membership_id=membership.id,
    )


def _owner_count(session: Session, org_id: uuid.UUID) -> int:
    """How many active owners this organization has — counted **under a lock**.

    The lock is the whole point, and it is not an optimization.

    Every guard in this module is a check-then-act: count the owners, then
    demote / disable / remove one. Without serialization that is a textbook
    TOCTOU race, and the outcome is the worst one this file exists to prevent.
    Two administrators pressing "demote" on the two remaining owners at the same
    moment each read a count of 2, each pass the guard, and each commit — and
    the organization is left with no owner at all, recoverable only by a support
    ticket and a hand-written UPDATE. It needs no malice and no unusual load;
    two browser tabs are enough.

    So the owner memberships are selected ``FOR UPDATE`` rather than counted
    with an aggregate. The rows themselves are locked for the caller's whole
    transaction, so a second request touching the same organization's owners
    blocks until the first commits and then re-reads the true count. ``of=`` is
    specified because the statement joins ``users``: without it Postgres would
    lock the user rows too, and an unrelated login touching that user would
    queue behind an administrative edit.

    On SQLite — every unit test — ``FOR UPDATE`` is silently omitted by the
    dialect, which is correct: the tests run one connection and cannot race.
    The property being defended is a Postgres one, and Postgres is what runs it.
    """

    owners = session.scalars(
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.org_id == org_id,
            Membership.role == OWNER,
            Membership.status == "active",
            User.status == "active",
        )
        .with_for_update(of=Membership)
    ).all()
    return len(owners)


@router.get("/members", response_model=AdminUserListOut)
def list_members(
    org: Annotated[OrgContext, Depends(requires(MEMBER_READ))],
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    account_status: Annotated[str | None, Query(alias="status", max_length=20)] = None,
    role: Annotated[str | None, Query(max_length=40)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminUserListOut:
    """Members of the caller's organization, searchable.

    Search is a case-insensitive substring over the email, which is the only
    human-readable identifier a user has today. It is applied in SQL rather
    than after fetching, so the limit means what it says on a large org.
    """

    base = (
        select(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.org_id == org.require_org_id)
    )
    if q:
        needle = f"%{q.strip().lower()}%"
        base = base.where(or_(func.lower(User.email).like(needle)))
    if account_status:
        base = base.where(User.status == account_status)
    if role:
        base = base.where(Membership.role == role)

    total = int(session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = session.execute(base.order_by(User.created_at.desc()).limit(limit).offset(offset)).all()

    return AdminUserListOut(
        total=total,
        limit=limit,
        offset=offset,
        assignable_roles=assignable_by(org.role),
        members=[_member_out(user, membership) for user, membership in rows],
    )


@router.get("/members/{user_id}", response_model=AdminMemberOut)
def read_member(
    user_id: uuid.UUID,
    org: Annotated[OrgContext, Depends(requires(MEMBER_READ))],
    session: Annotated[Session, Depends(get_session)],
) -> AdminMemberOut:
    row = session.execute(
        select(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.org_id == org.require_org_id, User.id == user_id)
    ).first()
    if row is None:
        # 404, not 403: a user outside this org is indistinguishable from one
        # that does not exist, so this cannot enumerate accounts.
        raise HTTPException(status_code=404, detail="member not found")
    return _member_out(*row)


@router.patch("/members/{user_id}", response_model=AdminMemberOut)
def update_member(
    user_id: uuid.UUID,
    payload: AdminMemberUpdateRequest,
    org: Annotated[OrgContext, Depends(requires(MEMBER_ROLE_CHANGE))],
    session: Annotated[Session, Depends(get_session)],
) -> AdminMemberOut:
    """Change a member's role, or enable/disable their account.

    Both guards below prevent the same class of accident — an organization
    locking itself out with no way back in except a support ticket.
    """

    row = session.execute(
        select(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.org_id == org.require_org_id, User.id == user_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="member not found")

    user, membership = row
    before = {"role": membership.role, "status": user.status}
    revoked_sessions = 0

    if user.id == org.user_id and (payload.role is not None or payload.status is not None):
        # Self-service demotion is the other way an org loses its last admin,
        # and it is always a mistake rather than an intent.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="you cannot change your own role or status",
        )

    if payload.role is not None:
        grantable = assignable_by(org.role)
        if payload.role not in grantable:
            raise HTTPException(
                status_code=422,
                detail=f"role must be one of: {', '.join(grantable)}",
            )
        if (
            membership.role == OWNER
            and payload.role != OWNER
            and _owner_count(session, org.require_org_id) <= 1
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="an organization must keep at least one active owner",
            )
        membership.role = payload.role

    if payload.status is not None:
        if payload.status not in {"active", "disabled"}:
            raise HTTPException(status_code=422, detail="status must be active or disabled")
        if (
            payload.status == "disabled"
            and membership.role == OWNER
            and _owner_count(session, org.require_org_id) <= 1
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="an organization must keep at least one active owner",
            )
        user.status = payload.status
        membership.status = "active" if payload.status == "active" else "deactivated"
        if payload.status == "disabled":
            # Otherwise "disabled" means "disabled from their next login", and
            # the person carries on working in the tab they already have open.
            revoked_sessions = revoke_all_sessions_for_user(session, user_id=user.id)

    after = {"role": membership.role, "status": user.status}
    audit.emit_change(
        session,
        action="member:update",
        context=org,
        actor_type="user",
        entity_type="user",
        entity_id=user.id,
        before=before,
        after=after,
        # NOT "sessions_revoked": the redactor matches the substring
        # "session" and would replace this count with "[redacted]". That is
        # the redactor being over-eager exactly as designed — it errs toward
        # destroying a harmless field rather than leaking a credential — so
        # the fix belongs here, in the key name, not there.
        detail={"devices_signed_out": revoked_sessions} if revoked_sessions else None,
    )
    session.commit()
    session.refresh(user)
    session.refresh(membership)
    return _member_out(user, membership)


@router.get("/organization", response_model=AdminOrganizationOut)
def read_organization(
    org: Annotated[OrgContext, Depends(requires(ORG_READ))],
    session: Annotated[Session, Depends(get_session)],
) -> AdminOrganizationOut:
    """The caller's own organization, with its member count."""

    organization = session.get(Organization, org.require_org_id)
    if organization is None:  # pragma: no cover - the context proved it exists
        raise HTTPException(status_code=404, detail="organization not found")

    members = int(
        session.scalar(
            select(func.count()).select_from(Membership).where(Membership.org_id == organization.id)
        )
        or 0
    )
    return AdminOrganizationOut(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        kind=organization.kind,
        status=organization.status,
        created_at=organization.created_at,
        member_count=members,
    )


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: uuid.UUID,
    org: Annotated[OrgContext, Depends(requires(MEMBER_REMOVE))],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """Remove a member's seat in this organization.

    This deletes the **membership**, never the user. Two different things are
    being confused whenever a product offers one button for both: the person may
    hold seats in other organizations, and their authored rows — analyses,
    audits, the audit trail itself — must survive their departure or the history
    becomes unreadable. Deleting the account is a GDPR path with a soft window
    (P7.5), not this.

    Guarded exactly like a role change, and for the same reason: removing the
    last owner, or removing yourself, is how an organization ends up with nobody
    who can administer it.
    """

    row = session.execute(
        select(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.org_id == org.require_org_id, User.id == user_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="member not found")

    user, membership = row

    if user.id == org.user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="you cannot remove yourself from the organization",
        )
    if membership.role == OWNER and _owner_count(session, org.require_org_id) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an organization must keep at least one active owner",
        )

    audit.emit(
        session,
        action="member:remove",
        context=org,
        actor_type="user",
        entity_type="user",
        entity_id=user.id,
        before={"email": user.email, "role": membership.role, "status": membership.status},
        after=None,
    )
    session.delete(membership)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------


def _invitation_out(
    invitation: Invitation, *, invited_by_email: str | None = None
) -> AdminInvitationOut:
    return AdminInvitationOut(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        status=invitation.status,
        expired=invitations.is_expired(invitation),
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        revoked_at=invitation.revoked_at,
        last_sent_at=invitation.last_sent_at,
        sent_count=invitation.sent_count,
        invited_by_email=invited_by_email,
    )


def _inviter_emails(session: Session, rows: list[Invitation]) -> dict[uuid.UUID, str]:
    """Resolve inviter ids to addresses in one query rather than one per row."""

    ids = {row.invited_by_user_id for row in rows if row.invited_by_user_id is not None}
    if not ids:
        return {}
    return {
        user_id: email
        for user_id, email in session.execute(
            select(User.id, User.email).where(User.id.in_(ids))
        ).all()
    }


def _accept_url(settings: Settings, token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/invite/{token}"


@router.get("/invitations", response_model=AdminInvitationListOut)
def list_invitations(
    org: Annotated[OrgContext, Depends(requires(MEMBER_READ))],
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    invitation_status: Annotated[str | None, Query(alias="status", max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminInvitationListOut:
    """Outstanding and historical invitations for the caller's organization.

    Readable by anyone who may read members (`member:read`), because "who has
    been invited" is part of the same question as "who is here" — and hiding it
    from a Manager who can invite would make the list they created invisible
    to them.
    """

    total, rows = invitations.list_invitations(
        session,
        org_id=org.require_org_id,
        status=invitation_status,
        q=q,
        limit=limit,
        offset=offset,
    )
    emails = _inviter_emails(session, rows)
    return AdminInvitationListOut(
        total=total,
        limit=limit,
        offset=offset,
        assignable_roles=assignable_by(org.role),
        invitations=[
            _invitation_out(
                row,
                invited_by_email=(
                    emails.get(row.invited_by_user_id)
                    if row.invited_by_user_id is not None
                    else None
                ),
            )
            for row in rows
        ],
    )


@router.post(
    "/invitations",
    response_model=AdminInvitationCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    payload: AdminInvitationCreateRequest,
    org: Annotated[OrgContext, Depends(requires(MEMBER_INVITE))],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AdminInvitationCreatedOut:
    """Invite someone to this organization with a role.

    The role is validated against ``ASSIGNABLE_ROLES`` — the same list the role
    picker uses, with the platform roles removed. Without that check this
    endpoint would be a way for any Manager to mint a Yanki Super Admin, which
    is precisely the escalation an invitation table invites.
    """

    grantable = assignable_by(org.role)
    if payload.role not in grantable:
        raise HTTPException(
            status_code=422,
            detail=f"role must be one of: {', '.join(grantable)}",
        )

    try:
        minted = invitations.create_invitation(
            session,
            org_id=org.require_org_id,
            email=payload.email,
            role=payload.role,
            invited_by_user_id=org.user_id,
            ttl=timedelta(days=settings.invitation_ttl_days),
        )
    except invitations.InvitationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    organization = session.get(Organization, org.require_org_id)
    org_name = organization.name if organization is not None else "your organization"
    inviter = session.get(User, org.user_id) if org.user_id else None

    audit.emit(
        session,
        action="invitation:create",
        context=org,
        actor_type="user",
        entity_type="invitation",
        entity_id=minted.invitation.id,
        after={
            "email": minted.invitation.email,
            "role": minted.invitation.role,
            "expires_at": minted.invitation.expires_at,
        },
    )
    session.commit()

    accept_url = _accept_url(settings, minted.token)
    # Sent AFTER the commit, deliberately. An email announcing an invitation the
    # transaction then rolled back is unrecallable; a committed invitation whose
    # email failed is recoverable with the link this response carries.
    sent = send_invitation_email(
        to=minted.invitation.email,
        organization_name=org_name,
        role_label=minted.invitation.role.replace("_", " "),
        accept_url=accept_url,
        invited_by=inviter.email if inviter is not None else None,
        expires_at=minted.invitation.expires_at,
        settings=settings,
    )

    session.refresh(minted.invitation)
    return AdminInvitationCreatedOut(
        invitation=_invitation_out(
            minted.invitation,
            invited_by_email=inviter.email if inviter is not None else None,
        ),
        accept_url=accept_url,
        email_sent=sent,
    )


@router.post("/invitations/{invitation_id}/resend", response_model=AdminInvitationCreatedOut)
def resend_invitation(
    invitation_id: uuid.UUID,
    org: Annotated[OrgContext, Depends(requires(MEMBER_INVITE))],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AdminInvitationCreatedOut:
    """Mint a fresh link for an existing invitation and email it again.

    The previous token stops working the moment this returns, which is what
    makes resend the fix for a link that went to the wrong inbox.
    """

    invitation = _invitation_or_404(session, org, invitation_id)
    try:
        minted = invitations.resend_invitation(
            session, invitation, ttl=timedelta(days=settings.invitation_ttl_days)
        )
    except invitations.InvitationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    organization = session.get(Organization, org.require_org_id)
    org_name = organization.name if organization is not None else "your organization"
    inviter = session.get(User, org.user_id) if org.user_id else None

    audit.emit(
        session,
        action="invitation:resend",
        context=org,
        actor_type="user",
        entity_type="invitation",
        entity_id=invitation.id,
        after={"email": invitation.email, "expires_at": invitation.expires_at},
        detail={"sent_count": invitation.sent_count},
    )
    session.commit()

    accept_url = _accept_url(settings, minted.token)
    sent = send_invitation_email(
        to=invitation.email,
        organization_name=org_name,
        role_label=invitation.role.replace("_", " "),
        accept_url=accept_url,
        invited_by=inviter.email if inviter is not None else None,
        expires_at=invitation.expires_at,
        settings=settings,
    )

    session.refresh(invitation)
    return AdminInvitationCreatedOut(
        invitation=_invitation_out(
            invitation, invited_by_email=inviter.email if inviter is not None else None
        ),
        accept_url=accept_url,
        email_sent=sent,
    )


@router.delete("/invitations/{invitation_id}", response_model=AdminInvitationOut)
def revoke_invitation(
    invitation_id: uuid.UUID,
    org: Annotated[OrgContext, Depends(requires(MEMBER_INVITE))],
    session: Annotated[Session, Depends(get_session)],
) -> AdminInvitationOut:
    """Withdraw a pending invitation. Its link stops working immediately.

    Returns the invitation rather than 204 so the UI can show it moved to
    'revoked' instead of guessing — the row stays as history, which is the point
    of revoking rather than deleting.
    """

    invitation = _invitation_or_404(session, org, invitation_id)
    before = {"status": invitation.status}
    try:
        invitations.revoke_invitation(session, invitation)
    except invitations.InvitationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    audit.emit_change(
        session,
        action="invitation:revoke",
        context=org,
        actor_type="user",
        entity_type="invitation",
        entity_id=invitation.id,
        before=before,
        after={"status": invitation.status},
    )
    session.commit()
    session.refresh(invitation)
    return _invitation_out(invitation)


def _invitation_or_404(session: Session, org: OrgContext, invitation_id: uuid.UUID) -> Invitation:
    """One invitation, scoped at the query. Another org's is a 404, not a 403."""

    invitation = session.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id, Invitation.org_id == org.require_org_id
        )
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail="invitation not found")
    return invitation


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

_INTEGRITY_LABEL: dict[bool | None, Literal["ok", "altered", "unverifiable"]] = {
    True: "ok",
    False: "altered",
    None: "unverifiable",
}


def _event_out(event: AuditEvent) -> AuditEventOut:
    detail = event.detail or {}
    changed = detail.get("changed") if isinstance(detail, dict) else None
    return AuditEventOut(
        id=event.id,
        occurred_at=event.occurred_at,
        action=event.action,
        outcome=event.outcome,
        actor_type=event.actor_type,
        actor_id=event.actor_id,
        actor_label=event.actor_label,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        before=event.before,
        after=event.after,
        changed=changed if isinstance(changed, dict) else None,
        ip_hash=event.ip_hash,
        user_agent=event.user_agent,
        request_id=event.request_id,
        integrity=_INTEGRITY_LABEL[audit.verify_row(event)],
    )


def _parse_moment(value: str | None, *, field: str) -> datetime | None:
    """An ISO-8601 date or datetime from a query string, as aware UTC.

    A bare date is accepted and means midnight UTC, because that is what a user
    typing into a date picker means. A naive datetime is read as UTC rather than
    as server-local: the server's timezone is an implementation detail nobody
    filtering a log should have to know.
    """

    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"{field} must be an ISO-8601 date or datetime"
        ) from exc
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


@router.get("/audit-events", response_model=AuditEventListOut)
def list_audit_events(
    org: Annotated[OrgContext, Depends(requires(AUDIT_READ))],
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    actor_id: Annotated[uuid.UUID | None, Query()] = None,
    entity_type: Annotated[str | None, Query(max_length=60)] = None,
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
    outcome: Annotated[str | None, Query(max_length=20)] = None,
    occurred_from: Annotated[str | None, Query(max_length=40)] = None,
    occurred_to: Annotated[str | None, Query(max_length=40)] = None,
    sort: Annotated[str, Query(max_length=40)] = audit.DEFAULT_SORT,
    order: Annotated[Literal["asc", "desc"], Query()] = "desc",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditEventListOut:
    """The organization's audit trail: filter, search, sort, page.

    **Org-scoped at the query.** ``org_id`` comes from the caller's context and
    is not a parameter, so there is no combination of filters that reaches
    another tenant's events — the platform-wide view is a different surface with
    a different permission (P7.7).

    An unknown ``sort`` falls back to ``occurred_at`` rather than erroring: a
    stale bookmark should show the log, not a validation message.
    """

    if sort not in audit.SORTABLE:
        sort = audit.DEFAULT_SORT

    page = audit.search_events(
        session,
        audit.EventQuery(
            org_id=org.require_org_id,
            q=q,
            action=action,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            outcome=outcome,
            occurred_from=_parse_moment(occurred_from, field="occurred_from"),
            occurred_to=_parse_moment(occurred_to, field="occurred_to"),
            sort=sort,
            descending=order == "desc",
            limit=limit,
            offset=offset,
        ),
    )

    return AuditEventListOut(
        total=page.total,
        limit=limit,
        offset=offset,
        sort=sort,
        order=order,
        actions=audit.distinct_actions(session, org_id=org.require_org_id),
        events=[_event_out(event) for event in page.events],
    )


#: The export's columns. A fixed, ordered tuple rather than "whatever the row
#: has", because a CSV whose columns move between exports is unusable to the
#: thing that actually consumes it — a spreadsheet, or an auditor's script.
_AUDIT_CSV_COLUMNS = (
    "occurred_at",
    "action",
    "outcome",
    "actor_type",
    "actor_label",
    "actor_id",
    "entity_type",
    "entity_id",
    "request_id",
    "record_hash",
    "integrity",
    "changed",
)

#: A hard ceiling, independent of the list view's 200. An export is meant to
#: cover a period, not a page — but it is still a synchronous request holding a
#: database connection, so it cannot be unbounded either. When an organization
#: outgrows this the answer is an export *artifact* (a job that produces a file),
#: not a bigger number here.
AUDIT_EXPORT_MAX = 5000


@router.get("/audit-events/export.csv", response_class=Response)
def export_audit_events_csv(
    org: Annotated[OrgContext, Depends(requires(AUDIT_READ))],
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    actor_id: Annotated[uuid.UUID | None, Query()] = None,
    entity_type: Annotated[str | None, Query(max_length=60)] = None,
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
    outcome: Annotated[str | None, Query(max_length=20)] = None,
    occurred_from: Annotated[str | None, Query(max_length=40)] = None,
    occurred_to: Annotated[str | None, Query(max_length=40)] = None,
    limit: Annotated[int, Query(ge=1, le=AUDIT_EXPORT_MAX)] = AUDIT_EXPORT_MAX,
) -> Response:
    """The filtered audit trail as CSV — and the export is itself audited.

    **Three things make this more than a formatting change.**

    *It takes the same filters as the list*, deliberately. An export that
    ignored them would hand someone the whole trail when they asked for one
    week of one actor, which is both less useful and more disclosure than they
    wanted. The filters are the same parameters, so a UI can export exactly
    what is on screen.

    *It carries the integrity verdict per row.* A trail that leaves this out is
    a spreadsheet of claims; with it, whoever receives the file can see that
    each row still hashes to its stored digest — ``intact``, ``altered``, or
    ``unverifiable`` for rows written before ``record_hash`` existed. The three
    answers are kept distinct here for the same reason
    :func:`audit.verify_row` keeps them: reporting a pre-hash row as *altered*
    cries wolf, and reporting it as *intact* is a claim the data cannot support.

    *Exporting is a disclosure event, so it emits one* (``audit:export``,
    admin-panel-plan §6). Somebody just took a copy of the compliance record
    out of the system; that is precisely the kind of action this table exists
    to remember, and an audit log that cannot say who exported it is missing
    the event most likely to matter afterwards. The row records the filters and
    the count, never the contents.

    **No secrets leave here that the API would not already show.** The rows go
    through ``_event_out``, so ``before``/``after`` are the same redacted
    payloads the list view serves; only the computed ``changed`` diff is
    flattened into the file, since a CSV cell cannot hold a nested object
    usefully.
    """

    page = audit.search_events(
        session,
        audit.EventQuery(
            org_id=org.require_org_id,
            q=q,
            action=action,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            outcome=outcome,
            occurred_from=_parse_moment(occurred_from, field="occurred_from"),
            occurred_to=_parse_moment(occurred_to, field="occurred_to"),
            sort=audit.DEFAULT_SORT,
            descending=True,
            limit=limit,
            offset=0,
        ),
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_AUDIT_CSV_COLUMNS)
    for event in page.events:
        verdict = audit.verify_row(event)
        out = _event_out(event)
        writer.writerow(
            [
                event.occurred_at.isoformat() if event.occurred_at else "",
                event.action,
                event.outcome or "",
                event.actor_type or "",
                event.actor_label or "",
                str(event.actor_id) if event.actor_id else "",
                event.entity_type or "",
                str(event.entity_id) if event.entity_id else "",
                event.request_id or "",
                event.record_hash or "",
                "intact" if verdict else ("unverifiable" if verdict is None else "altered"),
                json.dumps(out.changed, sort_keys=True) if out.changed else "",
            ]
        )

    audit.emit(
        session,
        action="audit:export",
        context=org,
        actor_type="user",
        actor_id=org.user_id,
        entity_type="audit_events",
        detail={
            "format": "csv",
            "rows": len(page.events),
            "matched": page.total,
            # Recorded so "what did they take?" is answerable. Only the filters
            # that were actually set, so the common unfiltered export does not
            # bury the interesting one under nine empty fields.
            "filters": {
                key: value
                for key, value in {
                    "q": q,
                    "action": action,
                    "actor_id": str(actor_id) if actor_id else None,
                    "entity_type": entity_type,
                    "entity_id": str(entity_id) if entity_id else None,
                    "outcome": outcome,
                    "occurred_from": occurred_from,
                    "occurred_to": occurred_to,
                }.items()
                if value
            },
            # The honest caveat, in the row itself: an export capped at the
            # ceiling may not be the whole answer, and whoever reads this event
            # later should not have to infer that from two numbers.
            "truncated": page.total > len(page.events),
        },
    )
    session.commit()

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit-events.csv"'},
    )


@router.get("/audit-events/history/{entity_type}/{entity_id}", response_model=AuditEventListOut)
def record_history(
    entity_type: str,
    entity_id: uuid.UUID,
    org: Annotated[OrgContext, Depends(requires(AUDIT_READ))],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditEventListOut:
    """Everything that ever touched one record — "what happened to this user?".

    Oldest first here, unlike the main log: a history is read as a story from
    the beginning, where a log is read from the latest thing that happened.
    """

    page = audit.search_events(
        session,
        audit.EventQuery(
            org_id=org.require_org_id,
            entity_type=entity_type,
            entity_id=entity_id,
            descending=False,
            limit=limit,
            offset=offset,
        ),
    )
    return AuditEventListOut(
        total=page.total,
        limit=limit,
        offset=offset,
        sort=audit.DEFAULT_SORT,
        order="asc",
        actions=[],
        events=[_event_out(event) for event in page.events],
    )


@router.get("/audit-events/integrity", response_model=AuditIntegrityOut)
def audit_integrity(
    org: Annotated[OrgContext, Depends(requires(AUDIT_READ))],
    session: Annotated[Session, Depends(get_session)],
) -> AuditIntegrityOut:
    """Re-hash this org's recent audit rows and report anything that changed.

    The honest scope of this check is stated in the audit module: it detects an
    edit to a row's content. Deletion is prevented at the database by the
    append-only trigger rather than detected here.
    """

    report = audit.verify_integrity(session, org_id=org.require_org_id)
    return AuditIntegrityOut(
        checked=report.checked,
        intact=report.intact,
        altered=report.altered,
        unverifiable=report.unverifiable,
        altered_ids=report.altered_ids,
        ok=report.ok,
    )
