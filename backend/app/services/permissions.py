"""RBAC: ten roles, resource:action permissions, deny by default (P7.2).

The model is `permission = role capability ∩ scope grant`, enforced at the API
layer, with the UI only reflecting what this says. Three properties matter more
than the specific grants:

**Deny by default.** :func:`can` returns False for an unknown role, an unknown
permission, or a missing context. Every failure mode of this function is a
refusal. That is the opposite of the convenient design — an unknown permission
returning True would make adding a resource silently open it to everyone — and
it is why the tests below assert on nonsense inputs.

**Permissions are strings, not an enum, not a table.** ``resource:action``, so
M2 adds ``backlink:view`` and M7 adds ``webhook:manage`` without a migration or
a deploy ordering problem. Roles are strings for the same reason: M8 turns them
into data (custom roles by clone-and-edit), and a database enumeration would
force a migration per role forever.

**Client roles are structurally isolated, not merely unlisted.** Guest cannot
reach billing, credits, internal notes or other workspaces because the grants
do not contain those permissions — and :func:`can` has no wildcard that could
accidentally include them. The one wildcard that exists, Super Admin's, is a
platform role no customer can hold.

The matrix below is the acceptance fixture: the planning baseline's §11.2 table,
transcribed. When it and the baseline disagree, the baseline wins and this file
changes.
"""

from __future__ import annotations

from app.services.tenancy import OrgContext

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

# Platform roles — Yanki staff. Cannot be held by a customer, and both are
# audited on every action (P7.3 records `actor_type='user'` with the role in
# detail; impersonation gets its own event at P7.7).
SUPER_ADMIN = "super_admin"
SUPPORT = "support"

# Organization roles.
OWNER = "owner"
ADMIN = "admin"
BILLING_ADMIN = "billing_admin"

# Workspace-scoped roles.
MANAGER = "manager"
EDITOR = "editor"
ANALYST = "analyst"
VIEWER = "viewer"
GUEST = "guest"

PLATFORM_ROLES = frozenset({SUPER_ADMIN, SUPPORT})
ORG_ROLES = frozenset({OWNER, ADMIN, BILLING_ADMIN})
WORKSPACE_ROLES = frozenset({MANAGER, EDITOR, ANALYST, VIEWER, GUEST})
ALL_ROLES = PLATFORM_ROLES | ORG_ROLES | WORKSPACE_ROLES

# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

# Organization + membership
ORG_READ = "org:read"
ORG_UPDATE = "org:update"
ORG_DELETE = "org:delete"
MEMBER_READ = "member:read"
MEMBER_INVITE = "member:invite"
MEMBER_ROLE_CHANGE = "member:role_change"
MEMBER_REMOVE = "member:remove"

# Workspaces + projects
WORKSPACE_READ = "workspace:read"
WORKSPACE_CREATE = "workspace:create"
WORKSPACE_UPDATE = "workspace:update"
PROJECT_READ = "project:read"
PROJECT_CREATE = "project:create"
PROJECT_UPDATE = "project:update"
PROJECT_DELETE = "project:delete"

# Work
ANALYSIS_RUN = "analysis:run"
ANALYSIS_READ = "analysis:read"
AUDIT_RUN = "site_audit:run"
BACKLINK_VIEW = "backlink:view"
BACKLINK_REFRESH = "backlink:refresh"

# Reports
REPORT_DRAFT = "report:draft"
REPORT_SEND = "report:send"

# Export is a DISTINCT permission, not a consequence of read. "Can see it" and
# "can take a copy of it away" are different questions, and agencies answer them
# differently for client seats.
EXPORT = "export:data"

# Money and governance
BILLING_READ = "billing:read"
BILLING_MANAGE = "billing:manage"
CREDIT_READ = "credit:read"
APIKEY_ISSUE = "apikey:issue"
AUDIT_READ = "audit:read"

# Platform back office
PLATFORM_READ = "platform:read"
PLATFORM_MANAGE = "platform:manage"
IMPERSONATE = "platform:impersonate"

ALL_PERMISSIONS = frozenset(
    {
        ORG_READ,
        ORG_UPDATE,
        ORG_DELETE,
        MEMBER_READ,
        MEMBER_INVITE,
        MEMBER_ROLE_CHANGE,
        MEMBER_REMOVE,
        WORKSPACE_READ,
        WORKSPACE_CREATE,
        WORKSPACE_UPDATE,
        PROJECT_READ,
        PROJECT_CREATE,
        PROJECT_UPDATE,
        PROJECT_DELETE,
        ANALYSIS_RUN,
        ANALYSIS_READ,
        AUDIT_RUN,
        BACKLINK_VIEW,
        BACKLINK_REFRESH,
        REPORT_DRAFT,
        REPORT_SEND,
        EXPORT,
        BILLING_READ,
        BILLING_MANAGE,
        CREDIT_READ,
        APIKEY_ISSUE,
        AUDIT_READ,
        PLATFORM_READ,
        PLATFORM_MANAGE,
        IMPERSONATE,
    }
)

# ---------------------------------------------------------------------------
# The matrix
# ---------------------------------------------------------------------------

_VIEWER: frozenset[str] = frozenset(
    {ORG_READ, WORKSPACE_READ, PROJECT_READ, ANALYSIS_READ, BACKLINK_VIEW}
)

# Guest is the client seat: free, unlimited, and structurally unable to see the
# commercial side of the account it is invited into. It is NOT "viewer minus a
# few things" — it is built up from nothing, so a permission added to Viewer
# later cannot leak into it by inheritance.
_GUEST: frozenset[str] = frozenset({PROJECT_READ, ANALYSIS_READ})

_ANALYST = _VIEWER | {ANALYSIS_RUN, AUDIT_RUN, BACKLINK_REFRESH, REPORT_DRAFT, EXPORT}
_EDITOR = _ANALYST | {PROJECT_CREATE, PROJECT_UPDATE, REPORT_SEND}
_MANAGER = _EDITOR | {
    WORKSPACE_CREATE,
    WORKSPACE_UPDATE,
    PROJECT_DELETE,
    MEMBER_READ,
    MEMBER_INVITE,
}

# Finance never needs data access. This is the clearest illustration of why the
# model is capability-based rather than a hierarchy: Billing Admin is powerful
# and sees almost nothing.
_BILLING_ADMIN = frozenset({ORG_READ, BILLING_READ, BILLING_MANAGE, CREDIT_READ})

_ADMIN = _MANAGER | {
    ORG_UPDATE,
    MEMBER_ROLE_CHANGE,
    MEMBER_REMOVE,
    APIKEY_ISSUE,
    AUDIT_READ,
    BILLING_READ,
    CREDIT_READ,
}
# Owner = Admin + the two things an admin must not do: delete the organization
# and buy things.
_OWNER = _ADMIN | {ORG_DELETE, BILLING_MANAGE}

_SUPPORT = frozenset(
    {PLATFORM_READ, ORG_READ, WORKSPACE_READ, PROJECT_READ, ANALYSIS_READ, AUDIT_READ}
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    GUEST: _GUEST,
    VIEWER: _VIEWER,
    ANALYST: frozenset(_ANALYST),
    EDITOR: frozenset(_EDITOR),
    MANAGER: frozenset(_MANAGER),
    BILLING_ADMIN: _BILLING_ADMIN,
    ADMIN: frozenset(_ADMIN),
    OWNER: frozenset(_OWNER),
    SUPPORT: _SUPPORT,
    # Super Admin is the only wildcard in the system, and it is a platform role
    # a customer cannot hold.
    SUPER_ADMIN: frozenset(ALL_PERMISSIONS),
}

# Permissions no client-lane role may EVER hold, whatever the matrix says. A
# second, independent check — because "Guest cannot see billing" is the kind of
# invariant that a well-meaning refactor of the grants above could break, and
# the failure would be silent.
CLIENT_FORBIDDEN = frozenset(
    {
        BILLING_READ,
        BILLING_MANAGE,
        CREDIT_READ,
        APIKEY_ISSUE,
        AUDIT_READ,
        MEMBER_INVITE,
        MEMBER_ROLE_CHANGE,
        MEMBER_REMOVE,
        ORG_UPDATE,
        ORG_DELETE,
        PLATFORM_READ,
        PLATFORM_MANAGE,
        IMPERSONATE,
    }
)
CLIENT_ROLES = frozenset({GUEST})


class PermissionDenied(RuntimeError):
    """Raised by :func:`require` when a caller may not do the thing."""

    def __init__(self, permission: str, role: str | None = None) -> None:
        super().__init__(f"role {role!r} may not {permission!r}")
        self.permission = permission
        self.role = role


def permissions_for(role: str | None) -> frozenset[str]:
    """Everything a role may do. Empty for anything unrecognised."""

    return ROLE_PERMISSIONS.get((role or "").strip().lower(), frozenset())


def can(context: OrgContext | None, permission: str) -> bool:
    """May this caller perform this action? Deny by default.

    Every uncertain answer is False: no context, no role, an unknown role, an
    unknown permission. An unknown permission returning True would mean adding
    a resource silently opens it to everyone, which is precisely the mistake
    this signature exists to make impossible.
    """

    if context is None or not permission:
        return False
    if permission not in ALL_PERMISSIONS:
        return False

    role = (getattr(context, "role", None) or "").strip().lower()
    if role in CLIENT_ROLES and permission in CLIENT_FORBIDDEN:
        return False
    return permission in permissions_for(role)


def require(context: OrgContext | None, permission: str) -> None:
    """:func:`can`, but raising. The form route dependencies use."""

    if not can(context, permission):
        raise PermissionDenied(permission, getattr(context, "role", None))
