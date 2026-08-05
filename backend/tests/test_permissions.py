"""RBAC (P7.2) — the matrix, and the ways it must fail.

Two kinds of test here, and the second kind matters more.

The first enumerates the baseline's §11.2 capability table: each role can do
what it should. Useful, but it is the easy half — a grant table trivially
satisfies its own enumeration.

The second asserts the *failure* behaviour, because every real permission bug
is a false positive. An unknown role must not be treated as a powerful one; an
unknown permission must not default to allowed; a client seat must not reach
billing even if somebody rewrites the grants above it. Those are the tests that
would actually catch a regression.
"""

from __future__ import annotations

import uuid

import pytest

from app.services import permissions as perm
from app.services.permissions import PermissionDenied, can, require
from app.services.tenancy import OrgContext


def ctx(role: str) -> OrgContext:
    return OrgContext(org_id=uuid.uuid4(), user_id=uuid.uuid4(), role=role)


# --------------------------------------------------------------------------
# Deny by default — every uncertain answer is False
# --------------------------------------------------------------------------


def test_no_context_can_do_nothing():
    assert can(None, perm.PROJECT_READ) is False


def test_an_unknown_role_can_do_nothing():
    assert can(ctx("wizard"), perm.PROJECT_READ) is False
    assert can(ctx(""), perm.PROJECT_READ) is False


def test_an_unknown_permission_is_denied_even_to_the_owner():
    """Otherwise adding a resource silently opens it to everyone."""

    assert can(ctx(perm.OWNER), "spaceship:launch") is False
    assert can(ctx(perm.SUPER_ADMIN), "spaceship:launch") is False


def test_an_empty_permission_is_denied():
    assert can(ctx(perm.OWNER), "") is False


def test_the_anonymous_and_system_contexts_hold_no_role_and_so_no_permission():
    assert can(OrgContext.public(), perm.PROJECT_READ) is False
    assert can(OrgContext.system(), perm.PROJECT_READ) is False


def test_require_raises_with_the_permission_and_role_named():
    with pytest.raises(PermissionDenied) as excinfo:
        require(ctx(perm.VIEWER), perm.BILLING_MANAGE)
    assert excinfo.value.permission == perm.BILLING_MANAGE
    assert excinfo.value.role == perm.VIEWER


def test_require_is_silent_when_allowed():
    require(ctx(perm.OWNER), perm.BILLING_MANAGE)


# --------------------------------------------------------------------------
# Client isolation — the structural property, checked two ways
# --------------------------------------------------------------------------


@pytest.mark.parametrize("permission", sorted(perm.CLIENT_FORBIDDEN))
def test_a_guest_can_never_reach_the_commercial_or_governance_lanes(permission):
    assert can(ctx(perm.GUEST), permission) is False


def test_a_guest_can_read_the_work_they_were_invited_to_see():
    assert can(ctx(perm.GUEST), perm.PROJECT_READ) is True
    assert can(ctx(perm.GUEST), perm.ANALYSIS_READ) is True


def test_a_guest_cannot_export():
    """Export is a distinct permission, and client seats do not get it."""

    assert can(ctx(perm.GUEST), perm.EXPORT) is False


def test_guest_grants_are_built_up_not_inherited_from_viewer():
    """So a permission added to Viewer later cannot leak into the client seat."""

    assert not perm.ROLE_PERMISSIONS[perm.GUEST] - perm.ROLE_PERMISSIONS[perm.VIEWER]
    assert perm.ROLE_PERMISSIONS[perm.GUEST] != perm.ROLE_PERMISSIONS[perm.VIEWER]


# --------------------------------------------------------------------------
# The matrix
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "permission", "allowed"),
    [
        # Owner is the only role that may delete the org or buy things.
        (perm.OWNER, perm.ORG_DELETE, True),
        (perm.ADMIN, perm.ORG_DELETE, False),
        (perm.OWNER, perm.BILLING_MANAGE, True),
        (perm.ADMIN, perm.BILLING_MANAGE, False),
        # Admin runs the org otherwise.
        (perm.ADMIN, perm.MEMBER_ROLE_CHANGE, True),
        (perm.ADMIN, perm.AUDIT_READ, True),
        (perm.MANAGER, perm.MEMBER_ROLE_CHANGE, False),
        # Finance sees money and no data.
        (perm.BILLING_ADMIN, perm.BILLING_MANAGE, True),
        (perm.BILLING_ADMIN, perm.CREDIT_READ, True),
        (perm.BILLING_ADMIN, perm.PROJECT_READ, False),
        (perm.BILLING_ADMIN, perm.ANALYSIS_READ, False),
        # Workspace ladder.
        (perm.MANAGER, perm.WORKSPACE_CREATE, True),
        (perm.EDITOR, perm.WORKSPACE_CREATE, False),
        (perm.EDITOR, perm.PROJECT_CREATE, True),
        (perm.ANALYST, perm.PROJECT_CREATE, False),
        (perm.ANALYST, perm.ANALYSIS_RUN, True),
        (perm.VIEWER, perm.ANALYSIS_RUN, False),
        # Analyst drafts but does not send.
        (perm.ANALYST, perm.REPORT_DRAFT, True),
        (perm.ANALYST, perm.REPORT_SEND, False),
        (perm.EDITOR, perm.REPORT_SEND, True),
        # Viewer reads and does not export.
        (perm.VIEWER, perm.PROJECT_READ, True),
        (perm.VIEWER, perm.EXPORT, False),
        (perm.ANALYST, perm.EXPORT, True),
        # Backlinks (M2) slot into the same model with no schema change.
        (perm.VIEWER, perm.BACKLINK_VIEW, True),
        (perm.VIEWER, perm.BACKLINK_REFRESH, False),
        (perm.ANALYST, perm.BACKLINK_REFRESH, True),
        # Platform roles.
        (perm.SUPPORT, perm.PLATFORM_READ, True),
        (perm.SUPPORT, perm.PLATFORM_MANAGE, False),
        (perm.SUPPORT, perm.ORG_UPDATE, False),
        (perm.SUPER_ADMIN, perm.PLATFORM_MANAGE, True),
        (perm.SUPER_ADMIN, perm.IMPERSONATE, True),
        (perm.OWNER, perm.IMPERSONATE, False),
    ],
)
def test_capability_matrix(role, permission, allowed):
    assert can(ctx(role), permission) is allowed


# --------------------------------------------------------------------------
# Invariants over the table itself
# --------------------------------------------------------------------------


def test_every_role_is_defined():
    assert set(perm.ROLE_PERMISSIONS) == set(perm.ALL_ROLES)


def test_every_granted_permission_is_a_declared_one():
    """A typo in a grant would otherwise be a silently dead permission."""

    for role, granted in perm.ROLE_PERMISSIONS.items():
        unknown = granted - perm.ALL_PERMISSIONS
        assert not unknown, f"{role} grants undeclared {unknown}"


def test_only_super_admin_holds_everything():
    for role, granted in perm.ROLE_PERMISSIONS.items():
        if role == perm.SUPER_ADMIN:
            assert granted == perm.ALL_PERMISSIONS
        else:
            assert granted != perm.ALL_PERMISSIONS


def test_no_customer_role_can_impersonate_or_manage_the_platform():
    for role in perm.ORG_ROLES | perm.WORKSPACE_ROLES:
        assert can(ctx(role), perm.IMPERSONATE) is False
        assert can(ctx(role), perm.PLATFORM_MANAGE) is False


def test_the_workspace_ladder_is_monotonic():
    """Each rung must contain the one below it, or the mental model is a lie."""

    ladder = [perm.VIEWER, perm.ANALYST, perm.EDITOR, perm.MANAGER]
    for lower, higher in zip(ladder, ladder[1:], strict=False):
        assert perm.ROLE_PERMISSIONS[lower] <= perm.ROLE_PERMISSIONS[higher], (
            f"{higher} should include everything {lower} has"
        )


def test_billing_admin_is_deliberately_not_on_the_ladder():
    """Powerful and blind — the clearest case for capabilities over hierarchy."""

    assert not perm.ROLE_PERMISSIONS[perm.VIEWER] <= perm.ROLE_PERMISSIONS[perm.BILLING_ADMIN]


def test_role_lookup_is_case_and_whitespace_insensitive():
    assert can(ctx("  OWNER  "), perm.ORG_DELETE) is True
