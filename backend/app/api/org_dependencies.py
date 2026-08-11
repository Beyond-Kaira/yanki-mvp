"""FastAPI dependency for "the organization this request acts within".

Split from ``auth_dependencies`` on purpose: authentication answers *who is
calling*, tenancy answers *on whose behalf*, and P7.2's permission model will
answer *may they*. Three questions, three seams — so the permission layer has a
place to land that is not tangled with token parsing.

Routes that read or write tenant-owned data depend on :func:`get_org_context`.
Routes on the anonymous public surface (``POST /analyses``, the checker, the
waitlist) depend on neither and are unchanged by this card.
"""

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth_dependencies import get_current_user, get_optional_user
from app.db.models import User
from app.db.session import get_session
from app.services import audit
from app.services.permissions import can
from app.services.tenancy import OrgContext, OrgScopeRequired, resolve_org_context


def get_org_context(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    x_org_id: Annotated[str | None, Header(alias="X-Org-Id")] = None,
) -> OrgContext:
    """Resolve the caller's organization, verifying membership.

    ``X-Org-Id`` lets a multi-org user pick which one they are acting in (the
    org switcher). It is a *request* for a scope, never a grant: membership is
    checked against the database every time, so naming an organization you do
    not belong to is a 403 rather than a read.

    Omitting the header selects the caller's first organization, which is the
    only one almost every user has.
    """

    org_id = None
    if x_org_id:
        try:
            org_id = uuid.UUID(x_org_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Org-Id is not a valid identifier",
            ) from exc

    try:
        return resolve_org_context(session, user=user, org_id=org_id)
    except OrgScopeRequired as exc:
        # 403, not 404: the caller is authenticated and the answer is "not for
        # you". Deliberately identical whether the organization does not exist
        # or merely is not theirs — distinguishing the two would let anyone
        # enumerate organization ids.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="no access to the requested organization",
        ) from exc


def get_optional_org_context(
    user: Annotated[User | None, Depends(get_optional_user)],
    session: Annotated[Session, Depends(get_session)],
    x_org_id: Annotated[str | None, Header(alias="X-Org-Id")] = None,
) -> OrgContext | None:
    """The caller's organization, or ``None`` when nobody is signed in.

    For routes that serve both audiences off one URL. ``GET /analyses/{id}`` is
    the reason it exists: an analysis with no organization is a capability URL
    anyone holding the id may read (every row created before P7.6, and every
    checker run), while one that *does* carry an organization is that
    organization's alone. The route cannot express both rules with a dependency
    that 401s the anonymous half.

    A signed-in caller gets the same treatment as ``get_org_context`` — a
    malformed ``X-Org-Id`` is still a 400 and an org they do not belong to is
    still a 403, because a client that named an organization meant it, and
    quietly resolving a different one would answer the wrong question.
    """

    if user is None:
        return None
    return get_org_context(user=user, session=session, x_org_id=x_org_id)


def requires(permission: str):
    """A route dependency that enforces one permission. Deny by default.

    Used as ``Depends(requires(PROJECT_CREATE))``. Returns the ``OrgContext``
    so a route needs only this one dependency rather than two — which matters
    because the failure mode of this design is a developer taking the context
    dependency and forgetting the permission one.

    A refusal is **403 and audited**: a denied attempt is often the event most
    worth having, and P7.3 records it with ``outcome='denied'``.
    """

    def _dependency(
        org: Annotated[OrgContext, Depends(get_org_context)],
        session: Annotated[Session, Depends(get_session)],
    ) -> OrgContext:
        if not can(org, permission):
            audit.emit(
                session,
                action=permission,
                context=org,
                actor_type="user",
                outcome="denied",
                detail={"reason": "permission_denied", "role": org.role},
            )
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="you do not have permission to perform this action",
            )
        return org

    return _dependency
