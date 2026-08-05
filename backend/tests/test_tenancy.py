"""Tenancy: the schema invariants, the backfill, and the isolation they buy (P7.1).

Grouped in one module because they are one argument. The card's acceptance is
four claims — additive migrations up and down, every pre-existing row reachable
through exactly one org, zero behaviour change for anonymous flows, cross-org
reads failing — and splitting the evidence across five files would make it
harder, not easier, to see whether the argument holds.

Everything here runs on SQLite. That is the point of putting the backfill in
``app.db.org_backfill`` rather than inside the migration: the real production
code path is exercised here, cheaply, with fixtures chosen to be nastier than
production (colliding local-parts, an unslugifiable email, a re-run). The
Postgres round-trip of the migration itself lives in ``test_migrations.py``.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    Analysis,
    Membership,
    Organization,
    Project,
    SeoProject,
    SiteAudit,
    User,
    Workspace,
)
from app.db.org_backfill import PUBLIC_ORG_ID, backfill_orgs, slugify, unique_slug
from app.services.auth import create_user
from app.services.seo_projects import (
    get_org_audit,
    get_org_project,
    list_org_projects,
)
from app.services.tenancy import (
    OrgContext,
    OrgScopeRequired,
    provision_personal_org,
    readable_analysis,
    resolve_org_context,
    scoped,
)


def _user(session, email: str) -> User:
    user = User(email=email, password_hash="x")
    session.add(user)
    session.flush()
    return user


def _org_for(session, user: User) -> Organization:
    org = provision_personal_org(session, user)
    session.commit()
    return org


# --------------------------------------------------------------------------
# Schema invariants — the constraints that make the service layer's job small
# --------------------------------------------------------------------------


def test_org_slug_is_globally_unique(db_session):
    db_session.add(Organization(name="A", slug="dup", kind="company"))
    db_session.commit()
    db_session.add(Organization(name="B", slug="dup", kind="company"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_user_can_only_have_one_personal_org(db_session):
    """The invariant that makes the signup race harmless."""

    user = _user(db_session, "solo@example.com")
    db_session.add(Organization(name="one", slug="one", kind="personal", owner_user_id=user.id))
    db_session.commit()
    db_session.add(Organization(name="two", slug="two", kind="personal", owner_user_id=user.id))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_user_may_own_many_company_orgs(db_session):
    """The partial index must constrain personal orgs and nothing else."""

    user = _user(db_session, "agency@example.com")
    db_session.add_all(
        [
            Organization(name="c1", slug="c1", kind="company", owner_user_id=user.id),
            Organization(name="c2", slug="c2", kind="company", owner_user_id=user.id),
        ]
    )
    db_session.commit()
    assert db_session.scalar(sa.select(sa.func.count()).select_from(Organization)) == 2


def test_only_one_default_workspace_per_org(db_session):
    org = Organization(name="A", slug="a", kind="company")
    db_session.add(org)
    db_session.flush()
    db_session.add(Workspace(org_id=org.id, name="W1", slug="w1", is_default=True))
    db_session.commit()
    db_session.add(Workspace(org_id=org.id, name="W2", slug="w2", is_default=True))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_membership_is_unique_per_org_and_user(db_session):
    user = _user(db_session, "m@example.com")
    org = Organization(name="A", slug="a", kind="company")
    db_session.add(org)
    db_session.flush()
    db_session.add(Membership(org_id=org.id, user_id=user.id, role="owner"))
    db_session.commit()
    db_session.add(Membership(org_id=org.id, user_id=user.id, role="admin"))
    with pytest.raises(IntegrityError):
        db_session.commit()


# --------------------------------------------------------------------------
# Slugs
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Alice", "alice"),
        ("first.last", "first-last"),
        ("a__b--c", "a-b-c"),
        ("  padded  ", "padded"),
        ("!!!", ""),
        ("ünïcode", "nïcode".encode("ascii", "ignore").decode() or "code"),
    ],
)
def test_slugify_normalizes_or_gives_up_honestly(raw, expected):
    result = slugify(raw)
    assert result == result.strip("-")
    assert all(c.isalnum() or c == "-" for c in result)


def test_unique_slug_cannot_return_a_taken_value():
    used = {"alice", "alice-2"}
    assert unique_slug("alice", used) == "alice-3"
    assert "alice-3" in used


def test_unique_slug_handles_an_empty_base():
    used: set[str] = set()
    assert unique_slug("", used) == "org"
    assert unique_slug("", used) == "org-2"


# --------------------------------------------------------------------------
# The backfill — run against the real function, on adversarial fixtures
# --------------------------------------------------------------------------


@pytest.fixture()
def seeded(db_session):
    """Three users with colliding and unslugifiable emails, two projects, one
    anonymous analysis."""

    alice_a = _user(db_session, "alice@a.example")
    alice_b = _user(db_session, "alice@b.example")
    punct = _user(db_session, "!!!@c.example")
    db_session.add_all(
        [
            SeoProject(
                user_id=alice_a.id,
                name="Acme",
                domain="https://acme.example/",
                domain_key="acme.example",
            ),
            SeoProject(
                user_id=alice_a.id,
                name="Beta",
                domain="https://beta.example/",
                domain_key="beta.example",
            ),
            Analysis(url="https://anon.example", status="done"),
        ]
    )
    db_session.commit()
    return {"alice_a": alice_a, "alice_b": alice_b, "punct": punct}


def test_backfill_gives_every_user_exactly_one_home(db_session, seeded):
    backfill_orgs(db_session.connection())
    db_session.commit()

    # Three personal orgs + the reserved public org.
    assert db_session.scalar(sa.select(sa.func.count()).select_from(Organization)) == 4
    assert (
        db_session.scalar(
            sa.select(sa.func.count())
            .select_from(Organization)
            .where(Organization.kind == "personal")
        )
        == 3
    )
    assert db_session.scalar(sa.select(sa.func.count()).select_from(Workspace)) == 3
    assert db_session.scalar(sa.select(sa.func.count()).select_from(Membership)) == 3
    assert all(
        m.role == "owner" and m.status == "active"
        for m in db_session.scalars(sa.select(Membership))
    )


def test_backfill_creates_the_reserved_public_org(db_session, seeded):
    backfill_orgs(db_session.connection())
    db_session.commit()

    public = db_session.get(Organization, PUBLIC_ORG_ID)
    assert public is not None
    assert public.kind == "system"
    assert public.owner_user_id is None


def test_backfill_resolves_slug_collisions_and_unslugifiable_emails(db_session, seeded):
    backfill_orgs(db_session.connection())
    db_session.commit()

    slugs = sorted(
        db_session.scalars(sa.select(Organization.slug).where(Organization.kind == "personal"))
    )
    assert len(slugs) == len(set(slugs)), "slugs must be unique"
    assert "alice" in slugs
    assert any(s.startswith("alice-") for s in slugs), "the collision got a suffix"
    # The all-punctuation local part still produced something usable.
    assert any(s.startswith("org") for s in slugs)


def test_backfill_links_every_seo_project_to_a_project_row(db_session, seeded):
    backfill_orgs(db_session.connection())
    db_session.commit()

    projects = list(db_session.scalars(sa.select(SeoProject)))
    assert len(projects) == 2
    for project in projects:
        db_session.refresh(project)
        assert project.org_id is not None
        assert project.workspace_id is not None
        assert project.project_id is not None
        tracked = db_session.get(Project, project.project_id)
        assert tracked is not None
        assert tracked.org_id == project.org_id
        assert tracked.domain_key == project.domain_key

    # One tracked business per site-audit project, not one per user.
    assert db_session.scalar(sa.select(sa.func.count()).select_from(Project)) == 2


def test_backfill_leaves_anonymous_analyses_unowned(db_session, seeded):
    backfill_orgs(db_session.connection())
    db_session.commit()

    analyses = list(db_session.scalars(sa.select(Analysis)))
    assert analyses, "fixture should have seeded one"
    assert all(a.org_id is None for a in analyses)


def test_backfill_is_idempotent(db_session, seeded):
    """A retried deploy, or a rollback-and-forward, must converge."""

    backfill_orgs(db_session.connection())
    db_session.commit()
    counts_first = {
        model.__name__: db_session.scalar(sa.select(sa.func.count()).select_from(model))
        for model in (Organization, Workspace, Membership, Project)
    }

    backfill_orgs(db_session.connection())
    db_session.commit()
    counts_second = {
        model.__name__: db_session.scalar(sa.select(sa.func.count()).select_from(model))
        for model in (Organization, Workspace, Membership, Project)
    }

    assert counts_first == counts_second


def test_backfill_on_an_empty_database_still_creates_the_public_org(db_session):
    backfill_orgs(db_session.connection())
    db_session.commit()
    assert db_session.get(Organization, PUBLIC_ORG_ID) is not None


# --------------------------------------------------------------------------
# Signup provisions a home, atomically
# --------------------------------------------------------------------------


def test_signup_creates_org_workspace_and_owner_membership(db_session):
    user = create_user(db_session, email="New.User@Example.com", password="hunter22")

    org = db_session.scalar(sa.select(Organization).where(Organization.owner_user_id == user.id))
    assert org is not None
    assert org.kind == "personal"
    assert org.slug == "new-user"

    workspace = db_session.scalar(sa.select(Workspace).where(Workspace.org_id == org.id))
    assert workspace is not None and workspace.is_default is True

    membership = db_session.scalar(sa.select(Membership).where(Membership.org_id == org.id))
    assert membership is not None
    assert membership.user_id == user.id
    assert membership.role == "owner"


def test_two_signups_with_the_same_local_part_get_distinct_slugs(db_session):
    create_user(db_session, email="chris@one.example", password="hunter22")
    create_user(db_session, email="chris@two.example", password="hunter22")

    slugs = sorted(db_session.scalars(sa.select(Organization.slug)))
    assert slugs == ["chris", "chris-2"]


def test_provisioning_twice_returns_the_same_org(db_session):
    user = _user(db_session, "again@example.com")
    first = provision_personal_org(db_session, user)
    db_session.commit()
    second = provision_personal_org(db_session, user)
    db_session.commit()
    assert first.id == second.id


def test_a_reserved_slug_is_never_handed_out(db_session):
    user = create_user(db_session, email="admin@example.com", password="hunter22")
    org = db_session.scalar(sa.select(Organization).where(Organization.owner_user_id == user.id))
    assert org is not None
    assert org.slug != "admin"


# --------------------------------------------------------------------------
# Cross-org isolation — the acceptance criterion with teeth
# --------------------------------------------------------------------------


@pytest.fixture()
def two_orgs(db_session):
    alice = _user(db_session, "alice@acme.example")
    bob = _user(db_session, "bob@globex.example")
    db_session.commit()
    org_a = _org_for(db_session, alice)
    org_b = _org_for(db_session, bob)

    project = SeoProject(
        user_id=alice.id,
        org_id=org_a.id,
        name="Acme",
        domain="https://acme.example/",
        domain_key="acme.example",
    )
    db_session.add(project)
    db_session.flush()
    audit = SiteAudit(project_id=project.id)
    db_session.add(audit)
    db_session.commit()

    return {
        "a": OrgContext(org_id=org_a.id, user_id=alice.id),
        "b": OrgContext(org_id=org_b.id, user_id=bob.id),
        "project": project,
        "audit": audit,
    }


def test_project_list_only_returns_the_callers_org(db_session, two_orgs):
    assert len(list_org_projects(db_session, two_orgs["a"].require_org_id)) == 1
    assert list_org_projects(db_session, two_orgs["b"].require_org_id) == []


def test_project_detail_is_invisible_across_orgs(db_session, two_orgs):
    project_id = two_orgs["project"].id
    assert (
        get_org_project(db_session, org_id=two_orgs["a"].require_org_id, project_id=project_id)
        is not None
    )
    assert (
        get_org_project(db_session, org_id=two_orgs["b"].require_org_id, project_id=project_id)
        is None
    )


def test_site_audit_is_scoped_through_its_project(db_session, two_orgs):
    """The child table carries no org column — the join is the isolation."""

    kwargs = {
        "project_id": two_orgs["project"].id,
        "audit_id": two_orgs["audit"].id,
    }
    assert get_org_audit(db_session, org_id=two_orgs["a"].require_org_id, **kwargs) is not None
    assert get_org_audit(db_session, org_id=two_orgs["b"].require_org_id, **kwargs) is None


def test_resolve_org_context_refuses_an_org_you_do_not_belong_to(db_session, two_orgs):
    alice = db_session.scalar(sa.select(User).where(User.email == "alice@acme.example"))
    with pytest.raises(OrgScopeRequired):
        resolve_org_context(db_session, user=alice, org_id=two_orgs["b"].org_id)


def test_resolve_org_context_accepts_an_org_you_do_belong_to(db_session, two_orgs):
    alice = db_session.scalar(sa.select(User).where(User.email == "alice@acme.example"))
    context = resolve_org_context(db_session, user=alice, org_id=two_orgs["a"].org_id)
    assert context.org_id == two_orgs["a"].org_id
    assert context.default_workspace_id is not None


def test_scoped_fails_closed_without_a_context():
    statement = sa.select(SeoProject)
    with pytest.raises(OrgScopeRequired):
        scoped(statement, SeoProject.org_id, None)
    with pytest.raises(OrgScopeRequired):
        scoped(statement, SeoProject.org_id, OrgContext.public())


def test_scoped_lets_a_system_caller_through_unfiltered():
    statement = sa.select(SeoProject)
    assert scoped(statement, SeoProject.org_id, OrgContext.system()) is statement


# --------------------------------------------------------------------------
# The public-scope read rule — the one place NULL means world-readable
# --------------------------------------------------------------------------


def test_a_null_org_analysis_is_readable_by_everyone(db_session, two_orgs):
    analysis = Analysis(url="https://anon.example", status="done")
    db_session.add(analysis)
    db_session.commit()

    for context in (None, OrgContext.public(), two_orgs["a"], two_orgs["b"], OrgContext.system()):
        assert readable_analysis(db_session, analysis.id, context) is not None


def test_an_owned_analysis_is_hidden_from_everyone_else(db_session, two_orgs):
    analysis = Analysis(url="https://owned.example", status="done", org_id=two_orgs["a"].org_id)
    db_session.add(analysis)
    db_session.commit()

    assert readable_analysis(db_session, analysis.id, two_orgs["a"]) is not None
    assert readable_analysis(db_session, analysis.id, OrgContext.system()) is not None
    # ...and invisible to the other tenant, and to the anonymous public.
    assert readable_analysis(db_session, analysis.id, two_orgs["b"]) is None
    assert readable_analysis(db_session, analysis.id, OrgContext.public()) is None
    assert readable_analysis(db_session, analysis.id, None) is None


def test_readable_analysis_returns_none_for_a_missing_row(db_session):
    assert readable_analysis(db_session, uuid.uuid4(), OrgContext.system()) is None
