"""The three Search Console tables, and the constraints that carry the design.

Two of these constraints are the design, not decoration:

``google_connections`` is unique on ``(org_id, google_account_id)`` and **not**
on ``org_id``. An agency holds one Google account per client estate; a unique
``org_id`` would force them to disconnect one client to look at another. The
test that would pass under the wrong constraint is the interesting one.

``site_audit_search_console_links`` is the mirror image: unique on
``seo_project_id`` so a project has exactly one property and no screen has to
choose between two numbers, while ``google_connection_id`` repeats freely so one
account serves a whole estate.

Nothing here touches Google. These are schema invariants, exercised against the
in-memory SQLite the rest of the suite uses.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    GoogleConnection,
    GoogleOAuthState,
    Organization,
    SeoProject,
    SiteAuditSearchConsoleLink,
    User,
    Workspace,
)


@pytest.fixture(autouse=True)
def _enforce_foreign_keys(db_session: Session) -> None:
    """SQLite ignores foreign keys unless asked, and half this file is about them.

    Postgres enforces them unconditionally, so without this pragma the ON DELETE
    rules below would pass here by doing nothing and only ever be exercised in
    production. Issued before any DML in the session, because SQLite treats the
    pragma as a no-op inside an open transaction.
    """

    db_session.execute(sa.text("PRAGMA foreign_keys=ON"))
    assert db_session.execute(sa.text("PRAGMA foreign_keys")).scalar() == 1


@pytest.fixture()
def make_org(db_session: Session) -> Callable[..., tuple[User, Organization, SeoProject]]:
    """A user, their organization, its default workspace and one SEO project."""

    def _make(slug: str = "acme") -> tuple[User, Organization, SeoProject]:
        user = User(email=f"{slug}@example.test", password_hash="x")
        db_session.add(user)
        db_session.flush()

        org = Organization(name=slug.title(), slug=slug, kind="personal", owner_user_id=user.id)
        db_session.add(org)
        db_session.flush()

        workspace = Workspace(org_id=org.id, name="Default", slug="default", is_default=True)
        db_session.add(workspace)
        db_session.flush()

        project = SeoProject(
            user_id=user.id,
            org_id=org.id,
            workspace_id=workspace.id,
            name=f"{slug}.test",
            domain=f"https://{slug}.test/",
            domain_key=f"{slug}.test",
        )
        db_session.add(project)
        db_session.commit()
        return user, org, project

    return _make


def _connection(
    org: Organization,
    user: User,
    account_id: str = "google-sub-1",
) -> GoogleConnection:
    return GoogleConnection(
        org_id=org.id,
        google_account_id=account_id,
        google_account_email=f"{account_id}@gmail.test",
        scopes="openid email https://www.googleapis.com/auth/webmasters.readonly",
        refresh_token_ciphertext=b"gAAAAA-ciphertext-placeholder",
        connected_by_user_id=user.id,
    )


def _link(
    project: SeoProject,
    connection: GoogleConnection,
    site_url: str = "sc-domain:acme.test",
    property_type: str = "domain",
) -> SiteAuditSearchConsoleLink:
    return SiteAuditSearchConsoleLink(
        seo_project_id=project.id,
        google_connection_id=connection.id,
        site_url=site_url,
        property_type=property_type,
        permission_level="siteOwner",
    )


# --------------------------------------------------------------------------
# google_connections
# --------------------------------------------------------------------------


def test_a_connection_defaults_to_active_on_key_version_one(db_session, make_org):
    user, org, _ = make_org()

    connection = _connection(org, user)
    db_session.add(connection)
    db_session.commit()

    assert connection.status == "active"
    assert connection.encryption_key_version == 1
    assert connection.last_refreshed_at is None
    assert connection.created_at is not None


def test_one_org_may_connect_several_google_accounts(db_session, make_org):
    """The agency case. A unique org_id would fail here — that is the point."""

    user, org, _ = make_org()

    db_session.add(_connection(org, user, "google-sub-1"))
    db_session.add(_connection(org, user, "google-sub-2"))
    db_session.commit()

    stored = db_session.query(GoogleConnection).filter_by(org_id=org.id).all()
    assert {row.google_account_id for row in stored} == {"google-sub-1", "google-sub-2"}


def test_the_same_google_account_cannot_be_connected_twice_to_one_org(db_session, make_org):
    user, org, _ = make_org()

    db_session.add(_connection(org, user, "google-sub-1"))
    db_session.commit()

    db_session.add(_connection(org, user, "google-sub-1"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_two_orgs_may_each_connect_the_same_google_account(db_session, make_org):
    """A consultant's own account, used in two client tenants, is legitimate."""

    user_a, org_a, _ = make_org("acme")
    user_b, org_b, _ = make_org("globex")

    db_session.add(_connection(org_a, user_a, "shared-sub"))
    db_session.add(_connection(org_b, user_b, "shared-sub"))
    db_session.commit()

    assert db_session.query(GoogleConnection).count() == 2


def test_the_refresh_token_column_holds_bytes_not_text(db_session, make_org):
    """Ciphertext round-trips as bytes; nothing coerces it through str()."""

    user, org, _ = make_org()
    connection = _connection(org, user)
    connection.refresh_token_ciphertext = b"\x80\x81 not valid utf-8"
    db_session.add(connection)
    db_session.commit()
    db_session.expire_all()

    reloaded = db_session.get(GoogleConnection, connection.id)
    assert reloaded.refresh_token_ciphertext == b"\x80\x81 not valid utf-8"


# --------------------------------------------------------------------------
# google_oauth_states
# --------------------------------------------------------------------------


def test_an_oauth_state_records_who_started_the_flow(db_session, make_org):
    """The callback's only trustworthy source of identity."""

    user, org, project = make_org()

    state = GoogleOAuthState(
        state_hash="sha256-of-the-raw-state",
        code_verifier="pkce-verifier",
        org_id=org.id,
        user_id=user.id,
        seo_project_id=project.id,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    db_session.add(state)
    db_session.commit()

    assert state.consumed_at is None
    assert state.org_id == org.id
    assert state.user_id == user.id
    assert state.seo_project_id == project.id


def test_a_state_hash_cannot_repeat(db_session, make_org):
    """Uniqueness is what makes 'consume exactly once' implementable."""

    user, org, project = make_org()
    expires_at = datetime.now(UTC) + timedelta(minutes=10)

    for _ in range(2):
        db_session.add(
            GoogleOAuthState(
                state_hash="collision",
                code_verifier="pkce-verifier",
                org_id=org.id,
                user_id=user.id,
                seo_project_id=project.id,
                expires_at=expires_at,
            )
        )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_the_project_takes_its_pending_states_with_it(db_session, make_org):
    """A state naming a deleted project must not survive to be exchanged."""

    user, org, project = make_org()
    db_session.add(
        GoogleOAuthState(
            state_hash="doomed",
            code_verifier="pkce-verifier",
            org_id=org.id,
            user_id=user.id,
            seo_project_id=project.id,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    db_session.commit()

    db_session.delete(db_session.get(SeoProject, project.id))
    db_session.commit()

    assert db_session.query(GoogleOAuthState).count() == 0


# --------------------------------------------------------------------------
# site_audit_search_console_links
# --------------------------------------------------------------------------


def test_a_project_may_link_exactly_one_property(db_session, make_org):
    user, org, project = make_org()
    connection = _connection(org, user)
    db_session.add(connection)
    db_session.commit()

    db_session.add(_link(project, connection, "sc-domain:acme.test", "domain"))
    db_session.commit()

    db_session.add(_link(project, connection, "https://acme.test/", "url_prefix"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_one_connection_serves_many_projects(db_session, make_org):
    """One Google account usually owns a whole estate of properties."""

    user, org, first = make_org("acme")
    second = SeoProject(
        user_id=user.id,
        org_id=org.id,
        workspace_id=first.workspace_id,
        name="shop.acme.test",
        domain="https://shop.acme.test/",
        domain_key="shop.acme.test",
    )
    db_session.add(second)

    connection = _connection(org, user)
    db_session.add(connection)
    db_session.commit()

    db_session.add(_link(first, connection, "sc-domain:acme.test", "domain"))
    db_session.add(_link(second, connection, "https://shop.acme.test/", "url_prefix"))
    db_session.commit()

    assert db_session.query(SiteAuditSearchConsoleLink).count() == 2


def test_removing_the_connection_removes_the_links_that_depend_on_it(db_session, make_org):
    """A link to a property nothing can authenticate for is worse than no link."""

    user, org, project = make_org()
    connection = _connection(org, user)
    db_session.add(connection)
    db_session.commit()

    db_session.add(_link(project, connection))
    db_session.commit()

    db_session.delete(db_session.get(GoogleConnection, connection.id))
    db_session.commit()

    assert db_session.query(SiteAuditSearchConsoleLink).count() == 0


def test_the_site_url_is_stored_verbatim(db_session, make_org):
    """``sc-domain:`` is Google's own identifier and must survive unedited."""

    user, org, project = make_org()
    connection = _connection(org, user)
    db_session.add(connection)
    db_session.commit()

    db_session.add(_link(project, connection, "sc-domain:acme.test", "domain"))
    db_session.commit()
    db_session.expire_all()

    stored = db_session.query(SiteAuditSearchConsoleLink).one()
    assert stored.site_url == "sc-domain:acme.test"
    assert stored.property_type == "domain"


def test_a_link_needs_a_real_connection(db_session, make_org):
    _, _, project = make_org()

    db_session.add(
        SiteAuditSearchConsoleLink(
            seo_project_id=project.id,
            google_connection_id=uuid.uuid4(),
            site_url="sc-domain:acme.test",
            property_type="domain",
            permission_level="siteOwner",
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
