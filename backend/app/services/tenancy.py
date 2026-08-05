"""Organizations, workspaces, memberships — and the seam that scopes reads to them.

This module is the point of card P7.1. Three responsibilities:

1. **Giving a user a home.** Signup calls :func:`provision_personal_org`; the
   migration's backfill (``app.db.org_backfill``) does the same for users who
   predate it. A user never owns data directly — they hold a membership in an
   organization that owns it — so converting a solo account into a company
   account later is a role change, not a data migration.

2. **Making org scoping hard to forget.** :func:`scoped` welds an org predicate
   onto a SELECT and *requires* a context rather than defaulting to "all rows".
   The failure modes are not symmetrical: a filter that defaults to everything
   leaks another tenant's data; one that defaults to nothing shows an empty
   screen. Only one of those is an incident.

3. **Deciding what "public" means.** :func:`readable_analysis` is the single
   place the NULL-org-is-world-readable rule lives. Confining it to one function
   is deliberate — a rule spread across call sites is a rule that will be
   applied where it should not be.

What this module does NOT do is decide whether a caller *may* act. Roles are
opaque strings here; interpreting them is P7.2's permission model, and keeping
authz out of the scoping layer leaves ``can(actor, resource:action, scope)``
exactly one home to land in.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.models import Analysis, Membership, Organization, Project, User, Workspace
from app.db.org_backfill import (
    DEFAULT_WORKSPACE_NAME,
    DEFAULT_WORKSPACE_SLUG,
    RESERVED_SLUGS,
    ROLE_OWNER,
    slugify,
)

__all__ = [
    "OrgContext",
    "OrgScopeRequired",
    "create_project",
    "default_workspace",
    "generate_unique_org_slug",
    "memberships_for_user",
    "provision_personal_org",
    "readable_analysis",
    "resolve_org_context",
    "scoped",
]


class OrgScopeRequired(RuntimeError):
    """Raised when a scoped query is attempted without an organization.

    Loud on purpose. A silent fallback to "no filter" is the exact bug this card
    exists to make impossible.
    """


@dataclass(frozen=True)
class OrgContext:
    """Who is asking, and on whose behalf.

    Resolved once per request from the caller's membership, then threaded
    through every query that request makes.

    ``is_system`` marks the workers and platform-admin paths, which legitimately
    read across tenants. It is a separate flag rather than a magic org id so
    that "this code bypasses tenant isolation" is a visible property of the
    caller rather than a value that could be forged into a request.
    """

    org_id: uuid.UUID | None
    user_id: uuid.UUID | None = None
    default_workspace_id: uuid.UUID | None = None
    # The caller's role in this org, as an opaque string. P7.2's permission
    # model interprets it; this module never does. Empty for the anonymous and
    # system contexts, which is why `can()` denies them by default.
    role: str = ""
    is_system: bool = False

    @classmethod
    def public(cls) -> OrgContext:
        """The anonymous caller — the entire live product surface today."""

        return cls(org_id=None)

    @classmethod
    def system(cls) -> OrgContext:
        """A worker or platform operation, which reads across organizations."""

        return cls(org_id=None, is_system=True)

    @property
    def require_org_id(self) -> uuid.UUID:
        """The org id, refusing to be None.

        Authenticated routes always have one; this makes that a checked fact
        rather than an assumption, and gives the type checker the narrowing it
        needs so a genuinely org-less context cannot reach a scoped query.
        """

        if self.org_id is None:
            raise OrgScopeRequired("this operation requires an organization")
        return self.org_id

    @property
    def require_user_id(self) -> uuid.UUID:
        """The acting user, refusing to be None. Same reasoning as above."""

        if self.user_id is None:
            raise OrgScopeRequired("this operation requires an authenticated user")
        return self.user_id


def generate_unique_org_slug(session: Session, base: str) -> str:
    """First free of ``base``, ``base-2``, ``base-3``, … avoiding reserved words.

    Mirrors ``org_backfill.unique_slug`` so a user provisioned at signup and one
    provisioned by the migration get slugs from the same rule. The pre-check
    races a concurrent signup; ``uq_organizations_slug`` is the real guarantee
    and the caller retries on IntegrityError.
    """

    root = slugify(base) or "org"
    candidate = root
    suffix = 1
    while candidate in RESERVED_SLUGS or session.scalar(
        select(Organization.id).where(Organization.slug == candidate)
    ):
        suffix += 1
        candidate = f"{root}-{suffix}"
    return candidate


def provision_personal_org(session: Session, user: User) -> Organization:
    """Create a user's personal org, its default workspace, and their ownership.

    Flushes but does **not** commit — the caller owns the transaction, because
    the only correct boundary is "user and org together or neither".

    Idempotent: returns the existing personal org if there is one, so a retried
    signup does not mint a second home. The database backs that up with
    ``uq_organizations_personal_owner``.
    """

    existing = session.scalar(
        select(Organization)
        .where(Organization.owner_user_id == user.id, Organization.kind == "personal")
        .order_by(Organization.created_at)
        .limit(1)
    )
    if existing is not None:
        return existing

    local_part = (user.email or "").split("@", 1)[0] or "account"
    org = Organization(
        name=f"{local_part}'s organization",
        slug=generate_unique_org_slug(session, local_part),
        kind="personal",
        status="active",
        owner_user_id=user.id,
    )
    session.add(org)
    session.flush()

    session.add(
        Workspace(
            org_id=org.id,
            name=DEFAULT_WORKSPACE_NAME,
            slug=DEFAULT_WORKSPACE_SLUG,
            is_default=True,
        )
    )
    session.add(Membership(org_id=org.id, user_id=user.id, role=ROLE_OWNER, status="active"))
    session.flush()
    return org


def default_workspace(session: Session, org_id: uuid.UUID) -> Workspace | None:
    """The workspace new projects land in — the one flagged, not the oldest.

    ``uq_workspaces_one_default_per_org`` guarantees there is at most one, so
    this has a single answer rather than a timestamp race.
    """

    return session.scalar(
        select(Workspace).where(Workspace.org_id == org_id, Workspace.is_default.is_(True))
    )


def memberships_for_user(session: Session, user_id: uuid.UUID) -> list[Membership]:
    """Every organization this user actively belongs to, oldest first.

    Returns a list even though almost every user has one entry, because
    multi-org membership (contractor mode) is supported from day one and a
    single-org assumption baked in here would have to be dug out later.
    """

    return list(
        session.scalars(
            select(Membership)
            .where(Membership.user_id == user_id, Membership.status == "active")
            .order_by(Membership.created_at)
        )
    )


def resolve_org_context(
    session: Session,
    *,
    user: User,
    org_id: uuid.UUID | None = None,
) -> OrgContext:
    """The organization a request acts within, and the caller's place in it.

    With no ``org_id``, the caller's first active membership. With one,
    membership is **verified, not trusted** — asking for an org you do not
    belong to raises, which is the check that stops a hand-crafted request from
    reading another tenant.

    Get-or-creates a personal org for a user who somehow has none, so an account
    created before this card (or by a half-failed signup) heals on next use
    instead of 403-ing forever.
    """

    memberships = memberships_for_user(session, user.id)

    if not memberships:
        org = provision_personal_org(session, user)
        session.commit()
        memberships = memberships_for_user(session, user.id)
        if not memberships:  # pragma: no cover - provisioning just succeeded
            raise OrgScopeRequired(f"user {user.id} belongs to no organization")
        del org

    chosen: Membership | None
    if org_id is None:
        chosen = memberships[0]
    else:
        chosen = next((m for m in memberships if m.org_id == org_id), None)
    if chosen is None:
        raise OrgScopeRequired(f"user {user.id} is not a member of organization {org_id}")

    workspace = default_workspace(session, chosen.org_id)
    return OrgContext(
        org_id=chosen.org_id,
        user_id=user.id,
        default_workspace_id=workspace.id if workspace is not None else None,
        role=chosen.role,
    )


def scoped(statement: Select, column, context: OrgContext | None) -> Select:
    """Weld an organization predicate onto a SELECT. Fails closed.

    ``column`` is passed in rather than inferred so the call site names the
    table it is scoping, and scoping the wrong table is visible in review.

    Raises on a missing or org-less context instead of quietly returning the
    unscoped statement. That is the whole safety property: there is no
    accidental path to every tenant's rows. A system caller opts out explicitly.
    """

    if context is None:
        raise OrgScopeRequired("an organization context is required for this query")
    if context.is_system:
        return statement
    if context.org_id is None:
        raise OrgScopeRequired("this query requires an organization, not the public scope")
    return statement.where(column == context.org_id)


def readable_analysis(
    session: Session,
    analysis_id: uuid.UUID,
    context: OrgContext | None = None,
) -> Analysis | None:
    """An analysis the caller is allowed to see, or None.

    **The one place the "NULL org is public" rule lives.** Every analysis in
    production today has ``org_id IS NULL`` and is served to anyone holding its
    id — a capability URL, and the product's entire live surface. That behaviour
    is preserved exactly.

    An analysis that *does* carry an org is visible to that org and to system
    callers, and to nobody else — including the anonymous public. Keeping this
    rule in a single function is deliberate: spread across call sites, "NULL
    means public" is one copy-paste away from being applied to a row that is not.
    """

    analysis = session.get(Analysis, analysis_id)
    if analysis is None:
        return None
    if analysis.org_id is None:
        return analysis
    if context is None:
        return None
    if context.is_system:
        return analysis
    if context.org_id is not None and analysis.org_id == context.org_id:
        return analysis
    return None


def create_project(
    session: Session,
    *,
    context: OrgContext,
    name: str,
    domain: str,
    domain_key: str,
    workspace_id: uuid.UUID | None = None,
    locale: str = "en",
) -> Project:
    """Register a tracked business in the caller's organization.

    ``workspace_id`` defaults to the org's default workspace, and when supplied
    is **validated against the caller's org** rather than accepted — a workspace
    id belonging to another tenant is precisely the request this layer refuses.
    """

    if context.org_id is None:
        raise OrgScopeRequired("creating a project requires an organization")

    if workspace_id is None:
        workspace = default_workspace(session, context.org_id)
        if workspace is None:
            raise OrgScopeRequired(f"organization {context.org_id} has no default workspace")
        workspace_id = workspace.id
    else:
        owned = session.scalar(
            select(Workspace.id).where(
                Workspace.id == workspace_id, Workspace.org_id == context.org_id
            )
        )
        if owned is None:
            raise OrgScopeRequired(
                f"workspace {workspace_id} does not belong to organization {context.org_id}"
            )

    project = Project(
        org_id=context.org_id,
        workspace_id=workspace_id,
        name=name,
        domain=domain,
        domain_key=domain_key,
        locale=locale,
        status="active",
    )
    session.add(project)
    session.flush()
    return project
