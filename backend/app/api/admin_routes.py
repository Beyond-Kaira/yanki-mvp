"""Administration: who is in this organization, and what may they do.

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

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.org_dependencies import requires
from app.api.schemas import (
    AdminMemberOut,
    AdminMemberUpdateRequest,
    AdminOrganizationOut,
    AdminUserListOut,
)
from app.db.models import Membership, Organization, User
from app.db.session import get_session
from app.services import audit
from app.services.permissions import (
    ALL_ROLES,
    MEMBER_READ,
    MEMBER_ROLE_CHANGE,
    ORG_READ,
    OWNER,
    PLATFORM_ROLES,
)
from app.services.tenancy import OrgContext

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# Roles an org administrator may assign. Platform roles are excluded on purpose:
# they are Yanki staff, and a customer must not be able to grant them.
ASSIGNABLE_ROLES = sorted(ALL_ROLES - PLATFORM_ROLES)


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
    return int(
        session.scalar(
            select(func.count())
            .select_from(Membership)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.org_id == org_id,
                Membership.role == OWNER,
                Membership.status == "active",
                User.status == "active",
            )
        )
        or 0
    )


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
        assignable_roles=ASSIGNABLE_ROLES,
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

    if user.id == org.user_id and (payload.role is not None or payload.status is not None):
        # Self-service demotion is the other way an org loses its last admin,
        # and it is always a mistake rather than an intent.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="you cannot change your own role or status",
        )

    if payload.role is not None:
        if payload.role not in ASSIGNABLE_ROLES:
            raise HTTPException(
                status_code=422,
                detail=f"role must be one of: {', '.join(ASSIGNABLE_ROLES)}",
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
