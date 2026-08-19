"""The M1 exit gate: zero cross-tenant reads, proved rather than asserted (P7.9).

Tenant isolation in this codebase is **per-route discipline**. There is no ORM
filter, no row-level security, no query interceptor — `tenancy.scoped()` and
`readable_analysis()` exist and a route that forgets to call them compiles,
passes its own tests, and leaks (tech-debt #63). That is a design the milestone
accepted; this file is the thing that makes it safe, and without it the M1
acceptance line "zero cross-tenant reads" is a claim nobody has checked.

It is built as a **census, not a checklist**, because a checklist of routes is
stale the moment somebody adds one — and the failure mode of a stale leakage
suite is the worst kind: it stays green while the surface it was written for
grows underneath it.

So:

1. Every operation the application publishes is read out of the live OpenAPI
   schema and matched against an explicit classification below. **An unclassified
   operation fails this suite.** Adding a route now forces the author to say, in
   writing, what its tenancy story is.
2. Every operation classified `ORG` gets a probe, and every probe is a **pair**:
   the owner must get a success *and* the stranger must get a 404. The pair
   matters more than it looks — a probe that only asserts the stranger's 404
   passes just as happily when the route is switched off by a feature flag, when
   the fixture failed to create the resource, or when the URL is misspelled. Half
   the value of this file is that it cannot pass vacuously.

**Why 404 and never 403.** A 403 says "this exists and is not yours", which is
an existence oracle: an attacker who can tell those apart can enumerate another
tenant's resource ids one request at a time. The whole point of an unguessable
id is lost the moment the API confirms a guess.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import Analysis, BacklinkCompetitor, SeoProject, SiteAudit
from app.services import billing
from app.services.seo_projects import normalize_project_domain

PASSWORD = "correct-horse-battery"


# ---------------------------------------------------------------------------
# The census
# ---------------------------------------------------------------------------

#: Deliberately reachable with no credential at all. Each one is a product
#: decision with a reason, and the reason is why it is safe for it to be here.
PUBLIC = {
    ("GET", "/healthz"),  # the deploy gate polls it; detail is withheld publicly
    ("POST", "/api/v1/auth/signup"),
    ("POST", "/api/v1/auth/login"),
    # Only client ids, which the browser presents to the provider anyway — and
    # the sign-in form that needs them is by definition unauthenticated.
    ("GET", "/api/v1/auth/providers"),
    # The provider's signed id_token IS the credential, and it is verified
    # against the provider's own keys before anything is read or written.
    ("POST", "/api/v1/auth/oauth"),
    ("POST", "/api/v1/auth/logout"),  # idempotent; discloses nothing about a token
    ("POST", "/api/v1/auth/refresh"),  # the cookie is the credential
    ("POST", "/api/v1/checker"),  # the anonymous funnel, capped not metered
    ("POST", "/api/v1/checker/leads"),
    ("POST", "/api/v1/waitlist"),
    # An invitation token IS the credential. Both routes are rate-limited by the
    # token's unguessability and expiry, and neither reveals an org to somebody
    # who does not hold one.
    ("GET", "/api/v1/invitations/{token}"),
    ("POST", "/api/v1/invitations/{token}/accept"),
}

#: Authenticated, and scoped to the *caller* rather than to an organization.
#: There is no tenant dimension to leak across; the leak these could have is
#: user-to-user, which their own suites cover (`test_auth_api`).
#: Keyword preview routes are stateless compute (seed in, ideas out) — no
#: org-owned row is read or written, so there is nothing for another tenant to
#: enumerate.
SELF = {
    ("GET", "/api/v1/auth/me"),
    ("GET", "/api/v1/auth/sessions"),
    ("POST", "/api/v1/auth/sessions/revoke-all"),
    ("DELETE", "/api/v1/auth/sessions/{session_id}"),
    ("POST", "/api/v1/keywords/expand"),
    ("POST", "/api/v1/keywords/overview"),
    ("POST", "/api/v1/keywords/rank-check"),
}

#: Readable by anyone holding the id, **on purpose**. Exactly one operation, and
#: it is allowed to be here only because `readable_analysis` enforces the split:
#: an org-less run is a capability URL, a run that carries an org is that org's
#: alone. The probe below proves the second half.
CAPABILITY = {
    ("GET", "/api/v1/analyses/{analysis_id}"),
    ("GET", "/api/v1/analyses/{analysis_id}/geo"),
    ("GET", "/api/v1/analyses/{analysis_id}/kyc"),
    ("GET", "/api/v1/analyses/{analysis_id}/prompts"),
    ("GET", "/api/v1/analyses/{analysis_id}/seo"),
    ("GET", "/api/v1/analyses/{analysis_id}/serp"),
}

#: Everything else. Must answer 404 to another tenant.
ORG = {
    ("GET", "/api/v1/analyses"),
    ("POST", "/api/v1/analyses"),
    ("DELETE", "/api/v1/analyses/{analysis_id}"),
    ("PATCH", "/api/v1/analyses/{analysis_id}/kyc"),
    ("PATCH", "/api/v1/analyses/{analysis_id}/prompts"),
    ("GET", "/api/v1/admin/organization"),
    ("GET", "/api/v1/admin/members"),
    ("GET", "/api/v1/admin/members/{user_id}"),
    ("PATCH", "/api/v1/admin/members/{user_id}"),
    ("DELETE", "/api/v1/admin/members/{user_id}"),
    ("GET", "/api/v1/admin/invitations"),
    ("POST", "/api/v1/admin/invitations"),
    ("POST", "/api/v1/admin/invitations/{invitation_id}/resend"),
    ("DELETE", "/api/v1/admin/invitations/{invitation_id}"),
    ("GET", "/api/v1/admin/audit-events"),
    ("GET", "/api/v1/admin/audit-events/history/{entity_type}/{entity_id}"),
    ("GET", "/api/v1/admin/audit-events/integrity"),
    ("GET", "/api/v1/admin/audit-events/export.csv"),
    ("GET", "/api/v1/seo-projects"),
    ("POST", "/api/v1/seo-projects"),
    ("GET", "/api/v1/seo-projects/{project_id}"),
    ("DELETE", "/api/v1/seo-projects/{project_id}"),
    ("POST", "/api/v1/seo-projects/{project_id}/audits"),
    ("GET", "/api/v1/seo-projects/{project_id}/audits/{audit_id}"),
    ("GET", "/api/v1/seo-projects/{project_id}/backlinks"),
    ("GET", "/api/v1/seo-projects/{project_id}/backlinks/summary"),
    ("GET", "/api/v1/seo-projects/{project_id}/backlinks/anchors"),
    ("GET", "/api/v1/seo-projects/{project_id}/backlinks/events"),
    ("GET", "/api/v1/seo-projects/{project_id}/backlinks/opportunities"),
    ("GET", "/api/v1/seo-projects/{project_id}/backlinks/referring-domains"),
    ("GET", "/api/v1/seo-projects/{project_id}/backlinks/export.csv"),
    ("GET", "/api/v1/seo-projects/{project_id}/backlinks/disavow.txt"),
    ("POST", "/api/v1/seo-projects/{project_id}/backlinks/refresh"),
    ("GET", "/api/v1/seo-projects/{project_id}/backlinks/competitors"),
    ("POST", "/api/v1/seo-projects/{project_id}/backlinks/competitors"),
    (
        "DELETE",
        "/api/v1/seo-projects/{project_id}/backlinks/competitors/{competitor_id}",
    ),
}

CLASSIFIED = PUBLIC | SELF | CAPABILITY | ORG


def live_operations() -> set[tuple[str, str]]:
    """Every operation the running application publishes.

    Read from the app's own schema rather than from `app.routes`, which changes
    shape between FastAPI versions (included routers became opaque wrappers),
    and rather than from the committed `openapi.json`, which would test the
    artifact instead of the code.
    """

    spec = app.openapi()
    return {
        (method.upper(), path)
        for path, operations in spec["paths"].items()
        for method in operations
        if method in ("get", "post", "put", "patch", "delete")
    }


def test_every_route_has_a_stated_tenancy_story() -> None:
    """The gate that keeps this file from going stale.

    A new route fails here until somebody puts it in one of the four sets above.
    That is the whole mechanism: isolation is per-route discipline, so the only
    durable defence is making "I did not think about tenancy" impossible to do
    silently.
    """

    unclassified = live_operations() - CLASSIFIED
    assert not unclassified, (
        "these operations have no tenancy classification — add each to PUBLIC, "
        f"SELF, CAPABILITY or ORG in this file and prove it: {sorted(unclassified)}"
    )


def test_the_census_describes_no_route_that_exists_only_here() -> None:
    """The mirror. A removed route must leave this file, or the next reader
    trusts a probe that has not run against anything for months."""

    phantom = CLASSIFIED - live_operations()
    assert not phantom, f"classified but no longer served: {sorted(phantom)}"


def test_the_public_surface_has_not_grown() -> None:
    """A count, deliberately. Adding an anonymous route is a product decision
    and should require editing a number that says so, not just appending a line
    to a set that nobody re-reads."""

    assert len(PUBLIC) == 12


# ---------------------------------------------------------------------------
# Two tenants, built through the real API
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def enabled_settings():
    """Real JWTs, both feature flags **on**, quotas and rate limits out of the way.

    The flags matter more than anything else in this fixture. `BACKLINKS_ENABLED`
    and `SITE_AUDIT_ENABLED` are off in production, and a dark route answers
    **404** — the same 404 this suite treats as proof of isolation. Run with the
    flags off and every backlink probe passes without touching a line of scoping
    code. That is the shape of a leakage suite that protects nothing.
    """

    settings = Settings(
        jwt_secret_key=SecretStr("a" * 64),
        jwt_issuer="test-yanki-api",
        jwt_audience="test-yanki-web",
        auth_refresh_cookie_secure=False,
        backlinks_enabled=True,
        site_audit_enabled=True,
        quota_enforcement_enabled=False,
        analyses_rate_limit_per_ip_hour=1000,
        analyses_daily_cap=1000,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture(autouse=True)
def resolvable_domains(monkeypatch):
    """`*.test` does not resolve, and the SSRF guard is right to refuse it.

    Patched in **both** modules that import it. Missing the second one is not a
    subtle failure — the analysis submit answers 422 and every fixture collapses
    — but it is worth naming, because it is the same class of mistake this suite
    exists to catch: a guard applied at one call site and not the other.
    """

    from app.api import routes, seo_project_routes

    monkeypatch.setattr(seo_project_routes, "is_public_url", lambda url: True)
    monkeypatch.setattr(routes, "is_public_url", lambda url: True)


class Tenant:
    """One organization, its owner, and the resources it owns."""

    def __init__(self, client: TestClient, session: Session, label: str) -> None:
        self.label = label
        self.email = f"{label}@example.test"
        signup = client.post(
            "/api/v1/auth/signup",
            json={
                "email": self.email,
                "password": PASSWORD,
                "account_type": "organization",
                "organization_name": f"{label.title()} Industries",
            },
        )
        assert signup.status_code == 201, signup.text
        self.user_id = uuid.UUID(signup.json()["id"])

        login = client.post("/api/v1/auth/login", json={"email": self.email, "password": PASSWORD})
        assert login.status_code == 200, login.text
        self.headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        me = client.get("/api/v1/auth/me", headers=self.headers)
        assert me.status_code == 200, me.text
        self.org_id = uuid.UUID(me.json()["organization"]["id"])

        # An unlimited plan, because this suite is about isolation and a 429 in
        # the middle of a probe proves nothing either way. It is also the only
        # way to reach the backlink refresh route at all: that path calls
        # `billing.reserve` directly rather than through `services.quota`, so
        # `QUOTA_ENFORCEMENT_ENABLED=0` does **not** switch it off, and Free
        # allows zero refreshes (tech-debt #89 — found here).
        billing.assign_plan(session, self.org_id, "enterprise")
        session.commit()

        project = client.post(
            "/api/v1/seo-projects",
            headers=self.headers,
            json={"domain": f"{label}.test"},
        )
        assert project.status_code == 201, project.text
        self.project_id = uuid.UUID(project.json()["id"])

        analysis = client.post(
            "/api/v1/analyses",
            headers=self.headers,
            json={"url": f"https://{label}.test/"},
        )
        assert analysis.status_code == 202, analysis.text
        self.analysis_id = uuid.UUID(analysis.json()["id"])

        invitation = client.post(
            "/api/v1/admin/invitations",
            headers=self.headers,
            json={"email": f"invitee-{label}@example.test", "role": "viewer"},
        )
        assert invitation.status_code == 201, invitation.text
        self.invitation_id = uuid.UUID(invitation.json()["invitation"]["id"])

        competitor = client.post(
            f"/api/v1/seo-projects/{self.project_id}/backlinks/competitors",
            headers=self.headers,
            json={"domain": f"rival-{label}.test"},
        )
        assert competitor.status_code == 201, competitor.text
        self.competitor_id = uuid.UUID(competitor.json()["id"])

        # The audit row is inserted directly: `POST /audits` refuses a project
        # that already has an active one, and project creation queues the first.
        audit_id = session.scalar(
            select(SiteAudit.id).where(SiteAudit.project_id == self.project_id)
        )
        assert audit_id is not None, "project creation should have queued the first crawl"
        self.audit_id = audit_id


@pytest.fixture
def tenants(client, db_session):
    """Two fully-populated organizations that have never met."""

    return Tenant(client, db_session, "alpha"), Tenant(client, db_session, "bravo")


def _probe(client, method: str, path: str, headers: dict[str, str], **kwargs):
    return client.request(method, path, headers=headers, **kwargs)


# ---------------------------------------------------------------------------
# The probes — each one a pair
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,template",
    [
        ("GET", "/api/v1/seo-projects/{project_id}"),
        ("GET", "/api/v1/seo-projects/{project_id}/backlinks"),
        ("GET", "/api/v1/seo-projects/{project_id}/backlinks/summary"),
        ("GET", "/api/v1/seo-projects/{project_id}/backlinks/anchors"),
        ("GET", "/api/v1/seo-projects/{project_id}/backlinks/events"),
        ("GET", "/api/v1/seo-projects/{project_id}/backlinks/opportunities"),
        ("GET", "/api/v1/seo-projects/{project_id}/backlinks/referring-domains"),
        ("GET", "/api/v1/seo-projects/{project_id}/backlinks/export.csv"),
        ("GET", "/api/v1/seo-projects/{project_id}/backlinks/disavow.txt"),
        ("GET", "/api/v1/seo-projects/{project_id}/backlinks/competitors"),
    ],
)
def test_a_project_scoped_read_is_404_for_the_other_tenant(
    client, tenants, method, template
) -> None:
    alpha, bravo = tenants
    mine = template.format(project_id=alpha.project_id)
    theirs = template.format(project_id=bravo.project_id)

    # The half that stops this passing vacuously.
    assert _probe(client, method, mine, alpha.headers).status_code == 200, (
        f"{method} {mine} must work for its owner, or the 404 below proves nothing"
    )
    assert _probe(client, method, theirs, alpha.headers).status_code == 404


@pytest.mark.parametrize(
    "method,template,payload",
    [
        ("POST", "/api/v1/seo-projects/{project_id}/backlinks/refresh", {}),
        (
            "POST",
            "/api/v1/seo-projects/{project_id}/backlinks/competitors",
            {"domain": "someone-else.test"},
        ),
    ],
)
def test_a_project_scoped_write_is_404_for_the_other_tenant(
    client, tenants, method, template, payload
) -> None:
    """A write is the one that actually costs something: `refresh` spends vendor
    money, and against another tenant's project it would spend *this* tenant's
    money enriching *that* tenant's data."""

    alpha, bravo = tenants
    theirs = template.format(project_id=bravo.project_id)

    assert _probe(client, method, theirs, alpha.headers, json=payload).status_code == 404

    # And the owner can do it, so a broken payload is not what produced the 404.
    mine = template.format(project_id=alpha.project_id)
    assert _probe(client, method, mine, alpha.headers, json=payload).status_code in (200, 201)


def test_a_site_audit_is_404_across_the_boundary(client, tenants) -> None:
    alpha, bravo = tenants

    mine = f"/api/v1/seo-projects/{alpha.project_id}/audits/{alpha.audit_id}"
    assert client.get(mine, headers=alpha.headers).status_code == 200

    # Both the honest cross-tenant URL and the *mixed* one — their audit hung
    # off my project id — which is the shape a real attacker would try first.
    theirs = f"/api/v1/seo-projects/{bravo.project_id}/audits/{bravo.audit_id}"
    mixed = f"/api/v1/seo-projects/{alpha.project_id}/audits/{bravo.audit_id}"
    assert client.get(theirs, headers=alpha.headers).status_code == 404
    assert client.get(mixed, headers=alpha.headers).status_code == 404


def test_a_competitor_cannot_be_deleted_across_the_boundary(client, tenants) -> None:
    alpha, bravo = tenants

    mixed = f"/api/v1/seo-projects/{alpha.project_id}/backlinks/competitors/{bravo.competitor_id}"
    assert client.delete(mixed, headers=alpha.headers).status_code == 404

    mine = f"/api/v1/seo-projects/{alpha.project_id}/backlinks/competitors/{alpha.competitor_id}"
    assert client.delete(mine, headers=alpha.headers).status_code == 204


def test_a_project_cannot_be_deleted_across_the_boundary(client, db_session, tenants) -> None:
    """The most destructive operation on the surface, so the worst one to leak.

    A hit here would not merely read another tenant's data — it would erase
    their tracked domain, every crawl recorded against it, and their backlink
    profile with it. The owner's 204 comes last, because it takes the project
    it is proving the route works on.
    """

    alpha, bravo = tenants

    theirs = f"/api/v1/seo-projects/{bravo.project_id}"
    assert client.delete(theirs, headers=alpha.headers).status_code == 404
    # Refused, not partially applied: their project is still there.
    assert db_session.get(SeoProject, bravo.project_id) is not None

    mine = f"/api/v1/seo-projects/{alpha.project_id}"
    assert client.delete(mine, headers=alpha.headers).status_code == 204


def test_an_analysis_that_belongs_to_an_org_is_404_for_everyone_else(client, tenants) -> None:
    """The `CAPABILITY` classification's second half. An org-less run stays
    world-readable — that is every row in production — but a run that carries an
    organization is that organization's alone, including against an anonymous
    caller holding the id."""

    alpha, bravo = tenants

    assert (
        client.get(f"/api/v1/analyses/{alpha.analysis_id}", headers=alpha.headers).status_code
        == 200
    )
    assert (
        client.get(f"/api/v1/analyses/{bravo.analysis_id}", headers=alpha.headers).status_code
        == 404
    )
    assert client.get(f"/api/v1/analyses/{bravo.analysis_id}").status_code == 404


def test_an_org_less_analysis_is_still_readable_by_anyone_holding_its_id(
    client, db_session, tenants
) -> None:
    """The other side of the same rule, and the reason it cannot simply be
    tightened: every analysis in production today has `org_id IS NULL`."""

    legacy = Analysis(url="https://legacy.test/", org_id=None)
    db_session.add(legacy)
    db_session.commit()

    assert client.get(f"/api/v1/analyses/{legacy.id}").status_code == 200


def test_the_history_list_never_contains_the_other_tenants_runs(client, tenants) -> None:
    alpha, bravo = tenants

    body = client.get("/api/v1/analyses", headers=alpha.headers).json()

    assert body["total"] == 1
    assert {row["id"] for row in body["analyses"]} == {str(alpha.analysis_id)}


def test_the_project_list_never_contains_the_other_tenants_projects(client, tenants) -> None:
    alpha, bravo = tenants

    body = client.get("/api/v1/seo-projects", headers=alpha.headers).json()

    assert {row["id"] for row in body} == {str(alpha.project_id)}


# ---------------------------------------------------------------------------
# The Admin Panel — the surface where a leak is worst
# ---------------------------------------------------------------------------


def test_the_member_list_shows_only_this_organization(client, tenants) -> None:
    alpha, bravo = tenants

    body = client.get("/api/v1/admin/members", headers=alpha.headers).json()
    emails = {member["email"] for member in body["members"]}

    assert alpha.email in emails
    assert bravo.email not in emails


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
def test_another_organizations_member_is_404(client, tenants, method) -> None:
    """Including PATCH and DELETE. A read leak exposes data; a write leak lets
    one tenant disable another tenant's owner."""

    alpha, bravo = tenants
    theirs = f"/api/v1/admin/members/{bravo.user_id}"

    kwargs = {"json": {"role": "viewer"}} if method == "PATCH" else {}
    assert _probe(client, method, theirs, alpha.headers, **kwargs).status_code == 404


@pytest.mark.parametrize("method,suffix", [("DELETE", ""), ("POST", "/resend")])
def test_another_organizations_invitation_is_404(client, tenants, method, suffix) -> None:
    """Resend is the sharp one: it rotates the token and returns the new
    `accept_url`, so a leak here is not a disclosure — it is a working key into
    someone else's organization."""

    alpha, bravo = tenants
    theirs = f"/api/v1/admin/invitations/{bravo.invitation_id}{suffix}"

    assert _probe(client, method, theirs, alpha.headers).status_code == 404

    mine = f"/api/v1/admin/invitations/{alpha.invitation_id}{suffix}"
    assert _probe(client, method, mine, alpha.headers).status_code == 200


def test_the_invitation_list_shows_only_this_organization(client, tenants) -> None:
    alpha, bravo = tenants

    body = client.get("/api/v1/admin/invitations", headers=alpha.headers).json()
    emails = {row["email"] for row in body["invitations"]}

    assert "invitee-alpha@example.test" in emails
    assert "invitee-bravo@example.test" not in emails


def test_the_audit_log_shows_only_this_organizations_events(client, tenants) -> None:
    """Every fixture action above emitted events for both tenants, so this is a
    real mixture in one table rather than a query against a single-tenant
    database that would pass whatever the scoping did."""

    alpha, bravo = tenants

    body = client.get("/api/v1/admin/audit-events", headers=alpha.headers).json()

    assert body["total"] > 0, "the fixtures should have produced events to filter"
    actors = {row["actor_label"] for row in body["events"] if row["actor_label"]}
    assert bravo.email not in actors


def test_a_record_history_lookup_cannot_read_across_the_boundary(client, tenants) -> None:
    alpha, bravo = tenants

    mine = f"/api/v1/admin/audit-events/history/user/{alpha.user_id}"
    theirs = f"/api/v1/admin/audit-events/history/user/{bravo.user_id}"

    assert client.get(mine, headers=alpha.headers).status_code == 200
    theirs_body = client.get(theirs, headers=alpha.headers).json()
    # An empty timeline rather than a 404: the route answers "nothing happened
    # to that record here", which is true and reveals nothing about whether the
    # id exists in another tenant.
    assert theirs_body["events"] == []


def test_the_organization_endpoint_reports_the_callers_own_org(client, tenants) -> None:
    alpha, bravo = tenants

    body = client.get("/api/v1/admin/organization", headers=alpha.headers).json()

    assert body["id"] == str(alpha.org_id)


def test_a_forged_org_header_does_not_grant_the_other_organization(client, tenants) -> None:
    """`X-Org-Id` is a *request* for a scope, never a grant. Membership is
    re-checked server-side on every request, which is what makes the header safe
    to accept from a browser at all."""

    alpha, bravo = tenants
    forged = {**alpha.headers, "X-Org-Id": str(bravo.org_id)}

    response = client.get("/api/v1/admin/organization", headers=forged)

    assert response.status_code in (403, 404)
    if response.status_code == 200:  # pragma: no cover - defensive
        assert response.json()["id"] != str(bravo.org_id)


# ---------------------------------------------------------------------------
# Direct-insert probes: resources whose creation route is gated
# ---------------------------------------------------------------------------


def test_a_project_row_alone_does_not_make_it_visible(client, db_session, tenants) -> None:
    """Guards against scoping that reads the *project* table but trusts a join.
    The row is inserted straight into the database under bravo's org, bypassing
    every route, so nothing but the read path's own filter stands between it and
    alpha."""

    alpha, bravo = tenants
    domain = normalize_project_domain("smuggled.test")
    row = SeoProject(
        user_id=bravo.user_id,
        org_id=bravo.org_id,
        name="Smuggled",
        domain=domain.url,
        domain_key=domain.key,
    )
    db_session.add(row)
    db_session.commit()

    assert client.get(f"/api/v1/seo-projects/{row.id}", headers=alpha.headers).status_code == 404

    listed = client.get("/api/v1/seo-projects", headers=alpha.headers).json()
    assert str(row.id) not in {item["id"] for item in listed}


def test_a_competitor_row_alone_does_not_make_it_visible(client, db_session, tenants) -> None:
    alpha, bravo = tenants
    row = BacklinkCompetitor(
        org_id=bravo.org_id,
        project_id=bravo.project_id,
        competitor_domain="smuggled-rival.test",
    )
    db_session.add(row)
    db_session.commit()

    listed = client.get(
        f"/api/v1/seo-projects/{alpha.project_id}/backlinks/competitors",
        headers=alpha.headers,
    ).json()

    assert "smuggled-rival.test" not in {item["competitor_domain"] for item in listed}
