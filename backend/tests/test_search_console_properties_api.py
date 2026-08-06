"""Connections, property selection and live performance, over real HTTP.

``test_search_console_api.py`` owns the OAuth flow. This owns everything after
it, and the properties worth stating are the ones a plausible implementation
gets wrong:

**Whose accounts.** Every read runs with a second organization holding its own
Google connection, so a missing tenant predicate cannot pass by being invisible.

**Whose word.** ``PUT /property`` takes a ``site_url`` from the client, and the
client is not evidence. The live list from Google decides, and
``permission_level`` is copied from the match rather than the request.

**What a token is for.** The refresh token is decrypted, spent on a short-lived
access token, and never written back or returned. A refusal marks the connection
``reauth_required``, which is the state the whole UI hangs off.

**What "no data" means.** A property with nothing to report is not an error and
is not zeros with a confident position — it is ``no_data`` with nulls.

Everything runs against ``MockGoogleOAuthProvider``. Nothing reaches Google.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.api.auth_dependencies import get_current_user
from app.api.main import app
from app.api.search_console_routes import get_provider
from app.config import Settings, get_settings
from app.db.models import (
    GoogleConnection,
    Membership,
    Organization,
    SeoProject,
    SiteAuditSearchConsoleLink,
    User,
    Workspace,
)
from app.gsc.base import SearchAnalyticsRow
from app.gsc.mock import MockGoogleOAuthProvider
from app.services.auth import hash_password
from app.services.token_crypto import encrypt_secret, generate_encryption_key

ENCRYPTION_KEY = generate_encryption_key()
CALLBACK_PATH = "/api/v1/integrations/google-search-console/callback"


@pytest.fixture()
def gsc_settings() -> Settings:
    return Settings(
        gsc_enabled=True,
        google_oauth_client_id="test-client.apps.googleusercontent.com",
        google_oauth_client_secret="test-client-secret",
        google_oauth_redirect_uri=f"http://localhost:8141{CALLBACK_PATH}",
        token_encryption_key=ENCRYPTION_KEY,
        public_base_url="http://localhost:8140",
    )


@pytest.fixture()
def provider() -> MockGoogleOAuthProvider:
    return MockGoogleOAuthProvider()


@pytest.fixture()
def enabled(gsc_settings, provider) -> Iterator[MockGoogleOAuthProvider]:
    app.dependency_overrides[get_settings] = lambda: gsc_settings
    app.dependency_overrides[get_provider] = lambda: provider
    yield provider
    app.dependency_overrides.pop(get_settings, None)
    app.dependency_overrides.pop(get_provider, None)


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_settings, None)
    app.dependency_overrides.pop(get_provider, None)


@pytest.fixture()
def make_org(db_session: Session, gsc_settings) -> Callable[..., dict]:
    """A tenant: user, org, workspace, project, and optionally a connection."""

    def _make(
        slug: str = "acme",
        *,
        role: str = "analyst",
        domain: str = "acme.test",
        connection: bool = True,
        refresh_token: str = "stored-refresh-token",
        status: str = "active",
        google_sub: str = "google-sub-1",
    ) -> dict:
        user = User(email=f"{slug}@example.test", password_hash=hash_password("correct-horse"))
        db_session.add(user)
        db_session.flush()

        org = Organization(name=slug, slug=slug, kind="personal", owner_user_id=user.id)
        db_session.add(org)
        db_session.flush()

        workspace = Workspace(org_id=org.id, name="Default", slug="default", is_default=True)
        db_session.add(workspace)
        db_session.flush()

        db_session.add(Membership(org_id=org.id, user_id=user.id, role=role, status="active"))

        project = SeoProject(
            user_id=user.id,
            org_id=org.id,
            workspace_id=workspace.id,
            name=domain,
            domain=f"https://{domain}/",
            domain_key=domain,
        )
        db_session.add(project)
        db_session.flush()

        google_connection = None
        if connection:
            google_connection = GoogleConnection(
                org_id=org.id,
                google_account_id=google_sub,
                google_account_email=f"{slug}-owner@example.test",
                scopes="email https://www.googleapis.com/auth/webmasters.readonly openid",
                status=status,
                refresh_token_ciphertext=encrypt_secret(refresh_token, settings=gsc_settings),
                connected_by_user_id=user.id,
            )
            db_session.add(google_connection)

        db_session.commit()
        return {
            "user": user,
            "org": org,
            "project": project,
            "connection": google_connection,
        }

    return _make


def _sign_in(user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


def _base(project: SeoProject) -> str:
    return f"/api/v1/seo-projects/{project.id}/search-console"


def _link(db_session: Session, tenant: dict, site_url: str = "sc-domain:acme.test") -> None:
    db_session.add(
        SiteAuditSearchConsoleLink(
            seo_project_id=tenant["project"].id,
            google_connection_id=tenant["connection"].id,
            site_url=site_url,
            property_type="domain",
            permission_level="siteOwner",
        )
    )
    db_session.commit()


# ==========================================================================
# GET /connections
# ==========================================================================


def test_connections_is_404_while_the_feature_is_off(client, make_org):
    tenant = make_org()
    _sign_in(tenant["user"])

    assert client.get(f"{_base(tenant['project'])}/connections").status_code == 404


def test_connections_requires_authentication(client, enabled, make_org):
    tenant = make_org()

    response = client.get(f"{_base(tenant['project'])}/connections")

    assert response.status_code in (401, 403)


def test_another_organizations_project_is_404(client, enabled, make_org):
    other = make_org("globex")
    intruder = make_org("acme")
    _sign_in(intruder["user"])

    response = client.get(f"{_base(other['project'])}/connections")

    assert response.status_code == 404


def test_only_this_organizations_google_accounts_are_listed(client, enabled, make_org):
    make_org("globex", google_sub="globex-sub")
    tenant = make_org("acme", google_sub="acme-sub")
    _sign_in(tenant["user"])

    payload = client.get(f"{_base(tenant['project'])}/connections").json()

    assert [row["google_account_email"] for row in payload["connections"]] == [
        "acme-owner@example.test"
    ]
    assert (
        "globex-owner@example.test"
        not in client.get(f"{_base(tenant['project'])}/connections").text
    )


def test_the_connections_response_carries_no_ciphertext_or_token(client, enabled, make_org):
    tenant = make_org()
    _sign_in(tenant["user"])

    response = client.get(f"{_base(tenant['project'])}/connections")

    body = response.text
    assert "refresh_token" not in body
    assert "ciphertext" not in body
    assert "stored-refresh-token" not in body
    assert set(response.json()["connections"][0]) == {
        "id",
        "google_account_email",
        "status",
        "scopes",
        "created_at",
        "updated_at",
        "selected_for_project",
        "selected_site_url",
    }


def test_the_scopes_are_returned_as_a_list(client, enabled, make_org):
    tenant = make_org()
    _sign_in(tenant["user"])

    row = client.get(f"{_base(tenant['project'])}/connections").json()["connections"][0]

    assert row["scopes"] == [
        "email",
        "https://www.googleapis.com/auth/webmasters.readonly",
        "openid",
    ]
    assert not any("analytics" in scope for scope in row["scopes"])


def test_project_status_reports_no_connection_when_there_is_none(client, enabled, make_org):
    tenant = make_org(connection=False)
    _sign_in(tenant["user"])

    payload = client.get(f"{_base(tenant['project'])}/connections").json()

    assert payload["project_status"] == "no_connection"
    assert payload["connections"] == []


def test_project_status_reports_an_unselected_property(client, enabled, make_org):
    tenant = make_org()
    _sign_in(tenant["user"])

    payload = client.get(f"{_base(tenant['project'])}/connections").json()

    assert payload["project_status"] == "no_property_selected"
    assert payload["connections"][0]["selected_for_project"] is False
    assert payload["connections"][0]["selected_site_url"] is None


def test_the_selected_connection_and_property_are_marked(client, enabled, make_org, db_session):
    tenant = make_org()
    _link(db_session, tenant, "sc-domain:acme.test")
    _sign_in(tenant["user"])

    payload = client.get(f"{_base(tenant['project'])}/connections").json()

    assert payload["project_status"] == "connected"
    assert payload["connections"][0]["selected_for_project"] is True
    assert payload["connections"][0]["selected_site_url"] == "sc-domain:acme.test"


def test_a_reauth_required_connection_is_visible_as_such(client, enabled, make_org, db_session):
    tenant = make_org(status="reauth_required")
    _link(db_session, tenant)
    _sign_in(tenant["user"])

    payload = client.get(f"{_base(tenant['project'])}/connections").json()

    assert payload["project_status"] == "reauth_required"
    assert payload["connections"][0]["status"] == "reauth_required"


def test_several_google_accounts_are_all_listed(
    client, enabled, make_org, db_session, gsc_settings
):
    tenant = make_org()
    db_session.add(
        GoogleConnection(
            org_id=tenant["org"].id,
            google_account_id="second-sub",
            google_account_email="second@example.test",
            scopes="openid",
            refresh_token_ciphertext=encrypt_secret("second-token", settings=gsc_settings),
        )
    )
    db_session.commit()
    _sign_in(tenant["user"])

    payload = client.get(f"{_base(tenant['project'])}/connections").json()

    assert len(payload["connections"]) == 2


# ==========================================================================
# GET /connections/{id}/properties
# ==========================================================================


def test_a_connection_from_another_org_is_404(client, enabled, make_org):
    other = make_org("globex", google_sub="globex-sub")
    tenant = make_org("acme", google_sub="acme-sub")
    _sign_in(tenant["user"])

    response = client.get(
        f"{_base(tenant['project'])}/connections/{other['connection'].id}/properties"
    )

    assert response.status_code == 404


def test_a_viewer_may_not_list_properties(client, enabled, make_org):
    """Listing spends a token refresh and a Search Console call."""

    tenant = make_org(role="viewer")
    _sign_in(tenant["user"])

    response = client.get(
        f"{_base(tenant['project'])}/connections/{tenant['connection'].id}/properties"
    )

    assert response.status_code == 403


def test_listing_properties_spends_the_decrypted_refresh_token(client, enabled, make_org):
    """Proof the ciphertext round-trip actually happened."""

    tenant = make_org(refresh_token="a-very-specific-token")
    _sign_in(tenant["user"])

    client.get(f"{_base(tenant['project'])}/connections/{tenant['connection'].id}/properties")

    assert enabled.refreshed_tokens == ["a-very-specific-token"]


def test_unverified_properties_are_not_offered(client, enabled, make_org):
    tenant = make_org()
    _sign_in(tenant["user"])

    payload = client.get(
        f"{_base(tenant['project'])}/connections/{tenant['connection'].id}/properties"
    ).json()

    assert all(item["permission_level"] != "siteUnverifiedUser" for item in payload["properties"])
    assert all("unverified.test" not in item["site_url"] for item in payload["properties"])


def test_matching_properties_are_suggested_and_sorted_first(client, enabled, make_org):
    tenant = make_org(domain="acme.test")
    _sign_in(tenant["user"])

    payload = client.get(
        f"{_base(tenant['project'])}/connections/{tenant['connection'].id}/properties"
    ).json()
    items = payload["properties"]

    # sc-domain:acme.test and https://www.acme.test/ both reduce to acme.test.
    assert [item["site_url"] for item in items[:2]] == [
        "https://www.acme.test/",
        "sc-domain:acme.test",
    ]
    assert all(item["matches_project_domain"] for item in items[:2])
    # shop.acme.test is a different host and must not be suggested.
    assert items[-1]["site_url"] == "https://shop.acme.test/"
    assert items[-1]["matches_project_domain"] is False


def test_the_property_types_are_derived_by_the_backend(client, enabled, make_org):
    tenant = make_org()
    _sign_in(tenant["user"])

    items = client.get(
        f"{_base(tenant['project'])}/connections/{tenant['connection'].id}/properties"
    ).json()["properties"]
    by_url = {item["site_url"]: item["property_type"] for item in items}

    assert by_url["sc-domain:acme.test"] == "domain"
    assert by_url["https://www.acme.test/"] == "url_prefix"


def test_the_selected_property_is_flagged(client, enabled, make_org, db_session):
    tenant = make_org()
    _link(db_session, tenant, "sc-domain:acme.test")
    _sign_in(tenant["user"])

    items = client.get(
        f"{_base(tenant['project'])}/connections/{tenant['connection'].id}/properties"
    ).json()["properties"]

    selected = [item for item in items if item["currently_selected"]]
    assert [item["site_url"] for item in selected] == ["sc-domain:acme.test"]


def test_the_ordering_is_deterministic_across_calls(client, enabled, make_org):
    tenant = make_org()
    _sign_in(tenant["user"])
    url = f"{_base(tenant['project'])}/connections/{tenant['connection'].id}/properties"

    first = [item["site_url"] for item in client.get(url).json()["properties"]]
    second = [item["site_url"] for item in client.get(url).json()["properties"]]

    assert first == second


def test_a_project_with_no_matching_property_still_gets_the_whole_list(client, enabled, make_org):
    tenant = make_org(domain="unrelated.test")
    _sign_in(tenant["user"])

    items = client.get(
        f"{_base(tenant['project'])}/connections/{tenant['connection'].id}/properties"
    ).json()["properties"]

    assert len(items) == 3
    assert not any(item["matches_project_domain"] for item in items)


def test_no_analytics_property_or_scope_appears_anywhere(client, enabled, make_org):
    tenant = make_org()
    _sign_in(tenant["user"])

    body = client.get(
        f"{_base(tenant['project'])}/connections/{tenant['connection'].id}/properties"
    ).text

    assert "analytics" not in body.lower()


# ==========================================================================
# PUT /property
# ==========================================================================


def test_a_site_url_the_account_cannot_reach_is_refused(client, enabled, make_org, db_session):
    """The client names a choice. It does not assert one."""

    tenant = make_org()
    _sign_in(tenant["user"])

    response = client.put(
        f"{_base(tenant['project'])}/property",
        json={
            "google_connection_id": str(tenant["connection"].id),
            "site_url": "sc-domain:someone-elses-site.test",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "property_not_accessible"
    assert db_session.query(SiteAuditSearchConsoleLink).count() == 0


def test_an_unverified_property_cannot_be_linked(client, enabled, make_org):
    """Filtered out of the offer, and equally refused if asked for by name."""

    tenant = make_org()
    _sign_in(tenant["user"])

    response = client.put(
        f"{_base(tenant['project'])}/property",
        json={
            "google_connection_id": str(tenant["connection"].id),
            "site_url": "https://unverified.test/",
        },
    )

    assert response.status_code == 409


def test_a_reachable_property_is_linked_with_googles_permission_level(
    client, enabled, make_org, db_session
):
    tenant = make_org()
    _sign_in(tenant["user"])

    response = client.put(
        f"{_base(tenant['project'])}/property",
        json={
            "google_connection_id": str(tenant["connection"].id),
            "site_url": "sc-domain:acme.test",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["site_url"] == "sc-domain:acme.test"
    assert payload["property_type"] == "domain"
    assert payload["permission_level"] == "siteOwner"
    assert payload["google_account_email"] == "acme-owner@example.test"

    link = db_session.query(SiteAuditSearchConsoleLink).one()
    assert link.site_url == "sc-domain:acme.test"
    assert link.permission_level == "siteOwner"


def test_the_permission_level_cannot_be_dictated_by_the_request(
    client, enabled, make_org, db_session
):
    tenant = make_org()
    _sign_in(tenant["user"])

    client.put(
        f"{_base(tenant['project'])}/property",
        json={
            "google_connection_id": str(tenant["connection"].id),
            "site_url": "https://shop.acme.test/",
            "permission_level": "siteOwner",
            "property_type": "domain",
        },
    )

    link = db_session.query(SiteAuditSearchConsoleLink).one()
    # The mock lists shop.acme.test as siteFullUser, and that is what is stored.
    assert link.permission_level == "siteFullUser"
    assert link.property_type == "url_prefix"


def test_changing_the_property_updates_the_same_row(client, enabled, make_org, db_session):
    tenant = make_org()
    _sign_in(tenant["user"])
    url = f"{_base(tenant['project'])}/property"

    client.put(
        url,
        json={
            "google_connection_id": str(tenant["connection"].id),
            "site_url": "sc-domain:acme.test",
        },
    )
    first_id = db_session.query(SiteAuditSearchConsoleLink).one().id

    client.put(
        url,
        json={
            "google_connection_id": str(tenant["connection"].id),
            "site_url": "https://www.acme.test/",
        },
    )

    db_session.expire_all()
    link = db_session.query(SiteAuditSearchConsoleLink).one()
    assert link.id == first_id
    assert link.site_url == "https://www.acme.test/"
    assert link.property_type == "url_prefix"


def test_linking_a_property_never_touches_another_projects_link(
    client, enabled, make_org, db_session
):
    tenant = make_org()
    sibling = SeoProject(
        user_id=tenant["user"].id,
        org_id=tenant["org"].id,
        workspace_id=tenant["project"].workspace_id,
        name="second",
        domain="https://second.test/",
        domain_key="second.test",
    )
    db_session.add(sibling)
    db_session.flush()
    db_session.add(
        SiteAuditSearchConsoleLink(
            seo_project_id=sibling.id,
            google_connection_id=tenant["connection"].id,
            site_url="https://shop.acme.test/",
            property_type="url_prefix",
            permission_level="siteFullUser",
        )
    )
    db_session.commit()
    _sign_in(tenant["user"])

    client.put(
        f"{_base(tenant['project'])}/property",
        json={
            "google_connection_id": str(tenant["connection"].id),
            "site_url": "sc-domain:acme.test",
        },
    )

    db_session.expire_all()
    sibling_link = (
        db_session.query(SiteAuditSearchConsoleLink).filter_by(seo_project_id=sibling.id).one()
    )
    assert sibling_link.site_url == "https://shop.acme.test/"
    assert db_session.query(SiteAuditSearchConsoleLink).count() == 2


def test_linking_never_deletes_a_google_connection(
    client, enabled, make_org, db_session, gsc_settings
):
    tenant = make_org()
    db_session.add(
        GoogleConnection(
            org_id=tenant["org"].id,
            google_account_id="second-sub",
            google_account_email="second@example.test",
            scopes="openid",
            refresh_token_ciphertext=encrypt_secret("second", settings=gsc_settings),
        )
    )
    db_session.commit()
    _sign_in(tenant["user"])

    client.put(
        f"{_base(tenant['project'])}/property",
        json={
            "google_connection_id": str(tenant["connection"].id),
            "site_url": "sc-domain:acme.test",
        },
    )

    assert db_session.query(GoogleConnection).count() == 2


def test_linking_through_another_orgs_connection_is_404(client, enabled, make_org, db_session):
    other = make_org("globex", google_sub="globex-sub")
    tenant = make_org("acme", google_sub="acme-sub")
    _sign_in(tenant["user"])

    response = client.put(
        f"{_base(tenant['project'])}/property",
        json={
            "google_connection_id": str(other["connection"].id),
            "site_url": "sc-domain:acme.test",
        },
    )

    assert response.status_code == 404
    assert db_session.query(SiteAuditSearchConsoleLink).count() == 0


def test_a_viewer_may_not_link_a_property(client, enabled, make_org):
    tenant = make_org(role="viewer")
    _sign_in(tenant["user"])

    response = client.put(
        f"{_base(tenant['project'])}/property",
        json={
            "google_connection_id": str(tenant["connection"].id),
            "site_url": "sc-domain:acme.test",
        },
    )

    assert response.status_code == 403


# ==========================================================================
# DELETE /property
# ==========================================================================


def test_unlinking_removes_the_link_and_keeps_the_connection(client, enabled, make_org, db_session):
    tenant = make_org()
    _link(db_session, tenant)
    _sign_in(tenant["user"])

    response = client.delete(f"{_base(tenant['project'])}/property")

    assert response.status_code == 204
    assert db_session.query(SiteAuditSearchConsoleLink).count() == 0
    assert db_session.query(GoogleConnection).count() == 1


def test_unlinking_leaves_other_projects_alone(client, enabled, make_org, db_session):
    tenant = make_org()
    _link(db_session, tenant)
    sibling = SeoProject(
        user_id=tenant["user"].id,
        org_id=tenant["org"].id,
        workspace_id=tenant["project"].workspace_id,
        name="second",
        domain="https://second.test/",
        domain_key="second.test",
    )
    db_session.add(sibling)
    db_session.flush()
    db_session.add(
        SiteAuditSearchConsoleLink(
            seo_project_id=sibling.id,
            google_connection_id=tenant["connection"].id,
            site_url="https://shop.acme.test/",
            property_type="url_prefix",
            permission_level="siteFullUser",
        )
    )
    db_session.commit()
    _sign_in(tenant["user"])

    client.delete(f"{_base(tenant['project'])}/property")

    remaining = db_session.query(SiteAuditSearchConsoleLink).all()
    assert [row.seo_project_id for row in remaining] == [sibling.id]


def test_unlinking_twice_is_a_success_both_times(client, enabled, make_org, db_session):
    tenant = make_org()
    _link(db_session, tenant)
    _sign_in(tenant["user"])

    first = client.delete(f"{_base(tenant['project'])}/property")
    second = client.delete(f"{_base(tenant['project'])}/property")

    assert first.status_code == 204
    assert second.status_code == 204


def test_a_viewer_may_not_unlink(client, enabled, make_org, db_session):
    tenant = make_org(role="viewer")
    _link(db_session, tenant)
    _sign_in(tenant["user"])

    assert client.delete(f"{_base(tenant['project'])}/property").status_code == 403
    assert db_session.query(SiteAuditSearchConsoleLink).count() == 1


# ==========================================================================
# Token refresh and reauth
# ==========================================================================


def test_a_refused_refresh_marks_the_connection_and_answers_409(
    client, enabled, make_org, db_session
):
    enabled.revoke_refresh = True
    tenant = make_org()
    _sign_in(tenant["user"])

    response = client.get(
        f"{_base(tenant['project'])}/connections/{tenant['connection'].id}/properties"
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "reauth_required"

    db_session.expire_all()
    assert db_session.get(GoogleConnection, tenant["connection"].id).status == "reauth_required"


def test_a_successful_refresh_clears_a_stale_reauth_flag(client, enabled, make_org, db_session):
    tenant = make_org(status="reauth_required")
    _sign_in(tenant["user"])

    client.get(f"{_base(tenant['project'])}/connections/{tenant['connection'].id}/properties")

    db_session.expire_all()
    connection = db_session.get(GoogleConnection, tenant["connection"].id)
    assert connection.status == "active"
    assert connection.last_refreshed_at is not None


def test_the_access_token_is_never_written_to_the_connection(client, enabled, make_org, db_session):
    tenant = make_org()
    _sign_in(tenant["user"])

    client.get(f"{_base(tenant['project'])}/connections/{tenant['connection'].id}/properties")

    db_session.expire_all()
    connection = db_session.get(GoogleConnection, tenant["connection"].id)
    stored = {
        column.name: getattr(connection, column.name) for column in connection.__table__.columns
    }
    assert "access_token" not in stored
    assert enabled.refreshed_access_token not in str(stored)


def test_the_access_token_never_reaches_a_response(client, enabled, make_org, db_session):
    tenant = make_org()
    _link(db_session, tenant)
    _sign_in(tenant["user"])

    bodies = [
        client.get(f"{_base(tenant['project'])}/connections").text,
        client.get(
            f"{_base(tenant['project'])}/connections/{tenant['connection'].id}/properties"
        ).text,
        client.get(f"{_base(tenant['project'])}/performance").text,
    ]

    for body in bodies:
        assert enabled.refreshed_access_token not in body
        assert "stored-refresh-token" not in body


# ==========================================================================
# GET /performance
# ==========================================================================


def _rows(clicks=100.0, impressions=1000.0, ctr=0.1, position=8.5):
    return {
        (): (
            SearchAnalyticsRow(
                keys=(), clicks=clicks, impressions=impressions, ctr=ctr, position=position
            ),
        ),
        ("query",): (
            SearchAnalyticsRow(
                keys=("running shoes",), clicks=60.0, impressions=500.0, ctr=0.12, position=4.2
            ),
            SearchAnalyticsRow(
                keys=("trail shoes",), clicks=40.0, impressions=500.0, ctr=0.08, position=12.8
            ),
        ),
        ("page",): (
            SearchAnalyticsRow(
                keys=("https://acme.test/shoes",),
                clicks=70.0,
                impressions=600.0,
                ctr=0.116,
                position=5.1,
            ),
        ),
    }


def test_performance_without_a_linked_property_is_409(client, enabled, make_org):
    tenant = make_org()
    _sign_in(tenant["user"])

    response = client.get(f"{_base(tenant['project'])}/performance")

    assert response.status_code == 409
    assert response.json()["detail"] == "no_property_selected"


def test_performance_with_a_reauth_required_connection_is_409(
    client, enabled, make_org, db_session
):
    tenant = make_org(status="reauth_required")
    _link(db_session, tenant)
    _sign_in(tenant["user"])

    response = client.get(f"{_base(tenant['project'])}/performance")

    assert response.status_code == 409
    assert response.json()["detail"] == "reauth_required"


def test_performance_normalizes_the_summary_and_both_lists(client, enabled, make_org, db_session):
    enabled.analytics_rows = _rows()
    tenant = make_org()
    _link(db_session, tenant)
    _sign_in(tenant["user"])

    payload = client.get(f"{_base(tenant['project'])}/performance").json()

    assert payload["site_url"] == "sc-domain:acme.test"
    assert payload["data_state"] == "ok"
    assert payload["summary"] == {
        "clicks": 100.0,
        "impressions": 1000.0,
        "ctr": 0.1,
        "position": 8.5,
    }
    assert [row["key"] for row in payload["top_queries"]] == ["running shoes", "trail shoes"]
    assert payload["top_queries"][0]["clicks"] == 60.0
    assert [row["key"] for row in payload["top_pages"]] == ["https://acme.test/shoes"]


def test_performance_uses_the_default_window_of_finalized_days(
    client, enabled, make_org, db_session
):
    enabled.analytics_rows = _rows()
    tenant = make_org()
    _link(db_session, tenant)
    _sign_in(tenant["user"])

    payload = client.get(f"{_base(tenant['project'])}/performance").json()

    start = date.fromisoformat(payload["start_date"])
    end = date.fromisoformat(payload["end_date"])
    assert (end - start).days == 27
    # Ends behind today, because Google revises the most recent days.
    assert end < datetime.now(UTC).date()


def test_performance_issues_exactly_three_bounded_queries(client, enabled, make_org, db_session):
    enabled.analytics_rows = _rows()
    tenant = make_org()
    _link(db_session, tenant)
    _sign_in(tenant["user"])

    client.get(f"{_base(tenant['project'])}/performance", params={"limit": 5})

    assert [q["dimensions"] for q in enabled.analytics_queries] == [(), ("query",), ("page",)]
    assert [q["row_limit"] for q in enabled.analytics_queries] == [1, 5, 5]
    assert all(q["site_url"] == "sc-domain:acme.test" for q in enabled.analytics_queries)


@pytest.mark.parametrize(
    "params",
    [
        {"start_date": "2026-05-01", "end_date": "2026-04-01"},
        {"end_date": "2099-01-01"},
        {"start_date": "1990-01-01"},
    ],
)
def test_an_impossible_window_is_422(client, enabled, make_org, db_session, params):
    tenant = make_org()
    _link(db_session, tenant)
    _sign_in(tenant["user"])

    response = client.get(f"{_base(tenant['project'])}/performance", params=params)

    assert response.status_code == 422


@pytest.mark.parametrize("limit", [0, 101, -1])
def test_a_limit_outside_the_bounds_is_422(client, enabled, make_org, db_session, limit):
    tenant = make_org()
    _link(db_session, tenant)
    _sign_in(tenant["user"])

    response = client.get(f"{_base(tenant['project'])}/performance", params={"limit": limit})

    assert response.status_code == 422


def test_an_explicit_window_is_honoured(client, enabled, make_org, db_session):
    enabled.analytics_rows = _rows()
    tenant = make_org()
    _link(db_session, tenant)
    _sign_in(tenant["user"])
    start = (datetime.now(UTC).date() - timedelta(days=40)).isoformat()
    end = (datetime.now(UTC).date() - timedelta(days=10)).isoformat()

    payload = client.get(
        f"{_base(tenant['project'])}/performance",
        params={"start_date": start, "end_date": end},
    ).json()

    assert payload["start_date"] == start
    assert payload["end_date"] == end
    assert enabled.analytics_queries[0]["start_date"] == start


def test_a_property_with_nothing_to_report_is_no_data_not_zeros(
    client, enabled, make_org, db_session
):
    enabled.analytics_rows = {(): (), ("query",): (), ("page",): ()}
    tenant = make_org()
    _link(db_session, tenant)
    _sign_in(tenant["user"])

    payload = client.get(f"{_base(tenant['project'])}/performance").json()

    assert payload["data_state"] == "no_data"
    assert payload["summary"]["clicks"] == 0
    assert payload["summary"]["impressions"] == 0
    # Null, not zero: an average over nothing is not zero, and position 0 would
    # read as "ranked above the first result".
    assert payload["summary"]["ctr"] is None
    assert payload["summary"]["position"] is None
    assert payload["top_queries"] == []
    assert payload["top_pages"] == []


def test_a_summary_row_with_no_impressions_yields_null_averages(
    client, enabled, make_org, db_session
):
    enabled.analytics_rows = {
        (): (SearchAnalyticsRow(keys=(), clicks=0.0, impressions=0.0, ctr=0.0, position=0.0),),
    }
    tenant = make_org()
    _link(db_session, tenant)
    _sign_in(tenant["user"])

    payload = client.get(f"{_base(tenant['project'])}/performance").json()

    assert payload["data_state"] == "no_data"
    assert payload["summary"]["ctr"] is None
    assert payload["summary"]["position"] is None


def test_top_rows_without_a_key_are_dropped_rather_than_rendered_blank(
    client, enabled, make_org, db_session
):
    enabled.analytics_rows = {
        (): (SearchAnalyticsRow(keys=(), clicks=10.0, impressions=100.0, ctr=0.1, position=3.0),),
        ("query",): (
            SearchAnalyticsRow(keys=(), clicks=5.0, impressions=50.0, ctr=0.1, position=2.0),
            SearchAnalyticsRow(
                keys=("real query",), clicks=5.0, impressions=50.0, ctr=0.1, position=4.0
            ),
        ),
    }
    tenant = make_org()
    _link(db_session, tenant)
    _sign_in(tenant["user"])

    payload = client.get(f"{_base(tenant['project'])}/performance").json()

    assert [row["key"] for row in payload["top_queries"]] == ["real query"]


def test_a_summary_is_never_invented_from_the_top_rows(client, enabled, make_org, db_session):
    """The per-query rows are a truncated top-N. Summing them would be wrong."""

    enabled.analytics_rows = {
        (): (),
        ("query",): (
            SearchAnalyticsRow(
                keys=("q",), clicks=999.0, impressions=9999.0, ctr=0.5, position=1.0
            ),
        ),
    }
    tenant = make_org()
    _link(db_session, tenant)
    _sign_in(tenant["user"])

    payload = client.get(f"{_base(tenant['project'])}/performance").json()

    assert payload["summary"]["clicks"] == 0
    assert payload["summary"]["impressions"] == 0
    assert payload["data_state"] == "no_data"


def test_a_rate_limited_provider_answers_429_with_retry_after(
    client, enabled, make_org, db_session
):
    enabled.rate_limited = True
    tenant = make_org()
    _link(db_session, tenant)
    _sign_in(tenant["user"])

    response = client.get(f"{_base(tenant['project'])}/performance")

    assert response.status_code == 429
    assert response.json()["detail"] == "provider_rate_limited"
    assert response.headers["retry-after"] == "30"


def test_a_lost_property_grant_is_reported_as_such_not_as_reauth(
    client, enabled, make_org, db_session
):
    """Reconnecting Google does not restore Search Console property access."""

    enabled.forbid_property = True
    tenant = make_org()
    _link(db_session, tenant)
    _sign_in(tenant["user"])

    response = client.get(f"{_base(tenant['project'])}/performance")

    assert response.status_code == 409
    assert response.json()["detail"] == "property_access_lost"


def test_an_unreadable_provider_body_is_502(client, enabled, make_org, db_session):
    enabled.malformed_analytics = True
    tenant = make_org()
    _link(db_session, tenant)
    _sign_in(tenant["user"])

    response = client.get(f"{_base(tenant['project'])}/performance")

    assert response.status_code == 502
    assert response.json()["detail"] == "malformed_provider_response"


def test_an_unreachable_provider_is_503_without_leaking_its_message(
    client, enabled, make_org, db_session
):
    enabled.fail_list_properties = True
    tenant = make_org()
    _sign_in(tenant["user"])

    response = client.get(
        f"{_base(tenant['project'])}/connections/{tenant['connection'].id}/properties"
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "provider_unavailable"
    assert "mock google" not in response.text


def test_performance_cannot_be_read_across_organizations(client, enabled, make_org, db_session):
    other = make_org("globex", domain="globex.test", google_sub="globex-sub")
    _link(db_session, other, "sc-domain:globex.test")
    tenant = make_org("acme", google_sub="acme-sub")
    _sign_in(tenant["user"])

    response = client.get(f"{_base(other['project'])}/performance")

    assert response.status_code == 404
    assert "globex" not in response.text


def test_a_link_pointing_at_an_invisible_connection_fails_closed(
    client, enabled, make_org, db_session
):
    """Defence in depth: a cross-org link must read as 'nothing selected'."""

    other = make_org("globex", google_sub="globex-sub")
    tenant = make_org("acme", google_sub="acme-sub")
    db_session.add(
        SiteAuditSearchConsoleLink(
            seo_project_id=tenant["project"].id,
            google_connection_id=other["connection"].id,
            site_url="sc-domain:globex.test",
            property_type="domain",
            permission_level="siteOwner",
        )
    )
    db_session.commit()
    _sign_in(tenant["user"])

    response = client.get(f"{_base(tenant['project'])}/performance")

    assert response.status_code == 409
    assert response.json()["detail"] == "no_property_selected"
    assert "globex" not in response.text
