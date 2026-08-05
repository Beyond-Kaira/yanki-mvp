"""The Backlink Intelligence HTTP surface (P8.3), over real HTTP.

``test_backlinks.py`` guards the engine's honesty — that it never invents a
loss. This file guards the three things only the boundary can get wrong, and
each has a plausible implementation that fails it:

**Darkness.** ``BACKLINKS_ENABLED=0`` must make the module indistinguishable
from a feature that does not exist. A 403 or an empty 200 both announce it, and
the flag is the only thing standing between an unfinished module and a customer
who finds it in the API docs.

**Who may spend.** Reading a profile and refreshing one are different acts: the
second calls a metered vendor. A Viewer holding ``backlink:view`` must not be
able to spend, and neither may they export — P7.2 keeps "can see it" and "can
take a copy away" as separate grants on purpose.

**Whose data.** Every read is checked with a second organization present, so a
missing tenant predicate cannot pass by being invisible in a single-tenant test.

Everything runs on the deterministic mock at $0.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from decimal import Decimal

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.auth_dependencies import get_current_user
from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import (
    AuditEvent,
    Backlink,
    BacklinkImport,
    CreditLedgerEntry,
    Membership,
    Organization,
    Plan,
    Project,
    SeoProject,
    Subscription,
    User,
    Workspace,
)
from app.services import billing
from app.services.auth import hash_password

DOMAIN = "acme.test"


def _url(project: SeoProject, suffix: str = "") -> str:
    return f"/api/v1/seo-projects/{project.id}/backlinks{suffix}"


@pytest.fixture()
def enabled_settings() -> Iterator[Settings]:
    """The module switched on, on the mock. DRY_RUN forces the mock regardless."""

    settings = Settings(backlinks_enabled=True, dry_run=True)
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def make_org(db_session: Session) -> Callable[..., tuple[User, SeoProject]]:
    """A user, their org, an active membership, and a tenancy-tracked project."""

    def _make(
        slug: str = "acme",
        *,
        role: str = "analyst",
        domain: str = DOMAIN,
        plan: str | None = "pro",
        credit: str = "10",
        tracked: bool = True,
    ) -> tuple[User, SeoProject]:
        user = User(email=f"{slug}@example.test", password_hash=hash_password("correct-horse"))
        org = Organization(name=slug.title(), slug=slug, kind="company")
        db_session.add_all([user, org])
        db_session.flush()
        workspace = Workspace(org_id=org.id, name="Default", slug="default", is_default=True)
        db_session.add(workspace)
        db_session.add(Membership(org_id=org.id, user_id=user.id, role=role, status="active"))
        db_session.flush()

        tracked_project = Project(
            org_id=org.id,
            workspace_id=workspace.id,
            name=slug.title(),
            domain=f"https://{domain}/",
            domain_key=domain,
        )
        db_session.add(tracked_project)
        db_session.flush()

        project = SeoProject(
            user_id=user.id,
            name=slug.title(),
            domain=f"https://{domain}/",
            domain_key=domain,
            org_id=org.id,
            workspace_id=workspace.id,
            project_id=tracked_project.id if tracked else None,
        )
        db_session.add(project)

        if plan is not None:
            billing.seed_plans(db_session)
            plan_row = db_session.scalar(sa.select(Plan).where(Plan.key == plan))
            db_session.add(Subscription(org_id=org.id, plan_id=plan_row.id, status="active"))
            db_session.flush()
            if Decimal(credit) > 0:
                billing.grant_credit(db_session, org.id, Decimal(credit))

        db_session.commit()
        return user, project

    return _make


def _as(user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


def _refresh(client: TestClient, project: SeoProject) -> dict:
    response = client.post(_url(project, "/refresh"), json={"trigger": "manual"})
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------
# Darkness — the kill switch is the whole safety story until A4 is answered
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "suffix",
    [
        "",
        "/summary",
        "/referring-domains",
        "/anchors",
        "/events",
        "/opportunities",
        "/competitors",
        "/export.csv",
        "/disavow.txt",
    ],
)
def test_every_read_is_404_while_the_flag_is_off(client, make_org, suffix) -> None:
    user, project = make_org()
    _as(user)

    assert client.get(_url(project, suffix)).status_code == 404


def test_refresh_is_404_while_the_flag_is_off(client, make_org) -> None:
    user, project = make_org()
    _as(user)

    assert client.post(_url(project, "/refresh"), json={}).status_code == 404


def test_the_flag_answers_before_authentication_does(client, make_org) -> None:
    """404 rather than 401 for an anonymous caller.

    A 401 would confirm the endpoint exists to anyone who asks, which is the
    one thing a kill switch is for.
    """

    _, project = make_org()

    assert client.get(_url(project, "/summary")).status_code == 404


def test_the_flag_on_makes_the_same_route_answer(client, make_org, enabled_settings) -> None:
    user, project = make_org()
    _as(user)

    response = client.get(_url(project, "/summary"))

    assert response.status_code == 200
    assert response.json()["subject_domain"] == DOMAIN


# --------------------------------------------------------------------------
# Permissions — reading, spending and exporting are three different grants
# --------------------------------------------------------------------------


def test_a_viewer_may_read_a_profile(client, make_org, enabled_settings) -> None:
    user, project = make_org(role="viewer")
    _as(user)

    assert client.get(_url(project, "/summary")).status_code == 200


def test_a_viewer_may_not_spend(client, make_org, enabled_settings, db_session) -> None:
    user, project = make_org(role="viewer")
    _as(user)

    response = client.post(_url(project, "/refresh"), json={})

    assert response.status_code == 403
    assert db_session.scalar(sa.select(sa.func.count()).select_from(BacklinkImport)) == 0


def test_a_viewer_may_not_export(client, make_org, enabled_settings) -> None:
    """``export:data`` is deliberately not implied by read — see P7.2."""

    user, project = make_org(role="viewer")
    _as(user)

    assert client.get(_url(project, "/export.csv")).status_code == 403
    assert client.get(_url(project, "/disavow.txt")).status_code == 403


def test_a_guest_may_not_even_read(client, make_org, enabled_settings) -> None:
    user, project = make_org(role="guest")
    _as(user)

    assert client.get(_url(project, "/summary")).status_code == 403


def test_a_refused_refresh_is_audited(client, make_org, enabled_settings, db_session) -> None:
    user, project = make_org(role="viewer")
    _as(user)

    client.post(_url(project, "/refresh"), json={})

    denied = db_session.scalar(
        sa.select(AuditEvent).where(
            AuditEvent.action == "backlink:refresh", AuditEvent.outcome == "denied"
        )
    )
    assert denied is not None


# --------------------------------------------------------------------------
# Tenancy — a second organization is present for every scoping assertion
# --------------------------------------------------------------------------


def test_another_orgs_project_is_indistinguishable_from_a_missing_one(
    client, make_org, enabled_settings
) -> None:
    user, _ = make_org("acme")
    _, other_project = make_org("rival", domain="rival.test")
    _as(user)

    response = client.get(_url(other_project, "/summary"))

    assert response.status_code == 404
    assert response.json()["detail"] == "SEO project not found"


def test_one_orgs_refresh_leaves_the_others_profile_empty(
    client, make_org, enabled_settings, db_session
) -> None:
    user, project = make_org("acme")
    other_user, other_project = make_org("rival", domain="rival.test")

    _as(user)
    _refresh(client, project)

    _as(other_user)
    summary = client.get(_url(other_project, "/summary")).json()
    assert summary["backlinks"] == 0
    assert summary["last_import"] is None


def test_a_project_without_a_tenancy_row_refuses_rather_than_writing_orphans(
    client, make_org, enabled_settings
) -> None:
    user, project = make_org(tracked=False)
    _as(user)

    response = client.get(_url(project, "/summary"))

    assert response.status_code == 409
    assert "workspace tracking" in response.json()["detail"]


# --------------------------------------------------------------------------
# Refresh — the metered path, end to end at $0
# --------------------------------------------------------------------------


def test_a_refresh_imports_a_profile_and_records_what_it_cost(
    client, make_org, enabled_settings, db_session
) -> None:
    user, project = make_org()
    _as(user)

    body = _refresh(client, project)

    assert body["rows_ingested"] > 0
    assert body["coverage_status"] == "complete"
    assert body["measurable"] is True

    record = db_session.get(BacklinkImport, uuid.UUID(body["import_id"]))
    assert record is not None
    assert record.status == "done"
    # The score is stamped by the service, not the importer, and must describe
    # the rollups this very import rebuilt.
    assert record.yanki_authority is not None
    assert record.authority_components

    ledger = db_session.scalar(
        sa.select(CreditLedgerEntry).where(CreditLedgerEntry.source_id == record.id)
    )
    assert ledger is not None, "a refresh that spends nothing still records that it ran"


def test_a_refresh_is_audited_with_its_outcome(
    client, make_org, enabled_settings, db_session
) -> None:
    user, project = make_org()
    _as(user)

    body = _refresh(client, project)

    event = db_session.scalar(
        sa.select(AuditEvent).where(
            AuditEvent.action == "backlink:refresh", AuditEvent.outcome == "success"
        )
    )
    assert event is not None
    assert event.after["subject_domain"] == DOMAIN
    assert event.after["rows_ingested"] == body["rows_ingested"]


def test_a_second_refresh_advances_the_cycle_rather_than_repeating_it(
    client, make_org, enabled_settings
) -> None:
    """The mock is a pure function of (domain, cycle), so a stuck cycle would
    make every refresh a no-op — and 'nothing ever changes' is indistinguishable
    from a broken importer."""

    user, project = make_org()
    _as(user)

    first = _refresh(client, project)
    second = _refresh(client, project)

    assert first["import_id"] != second["import_id"]
    assert second["new_links"] > 0


def test_events_accrue_across_refreshes(client, make_org, enabled_settings) -> None:
    user, project = make_org()
    _as(user)
    _refresh(client, project)
    _refresh(client, project)

    events = client.get(_url(project, "/events"), params={"kind": "new"}).json()

    assert events["total"] > 0
    assert {event["kind"] for event in events["items"]} == {"new"}


def test_a_concurrent_refresh_is_refused(client, make_org, enabled_settings, db_session) -> None:
    user, project = make_org()
    _as(user)
    tracked = db_session.scalar(sa.select(SeoProject).where(SeoProject.id == project.id))
    db_session.add(
        BacklinkImport(
            org_id=tracked.org_id,
            project_id=tracked.project_id,
            subject_domain=DOMAIN,
            status="running",
        )
    )
    db_session.commit()

    response = client.post(_url(project, "/refresh"), json={})

    assert response.status_code == 409


def test_an_exhausted_quota_is_429_not_a_generic_error(client, make_org, enabled_settings) -> None:
    """Free allows 0 backlink refreshes. The customer must be able to tell
    'you have used your plan' apart from 'the product is broken'."""

    user, project = make_org(plan="free")
    _as(user)

    response = client.post(_url(project, "/refresh"), json={})

    assert response.status_code == 429
    assert "quota" in response.json()["detail"]


def test_an_unimplemented_vendor_is_503_rather_than_an_empty_profile(client, make_org) -> None:
    """The A4 state: a vendor is named, its adapter is P8.2's job, and nothing
    exists behind it yet. The registry answers ``None`` rather than falling back
    to fixtures, so the surface must say 'not measured' — never 'no links'."""

    settings = Settings(backlinks_enabled=True, dry_run=False, backlink_vendor="dataforseo")
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        user, project = make_org()
        _as(user)
        response = client.post(_url(project, "/refresh"), json={})
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 503


# --------------------------------------------------------------------------
# The views
# --------------------------------------------------------------------------


def test_the_summary_reports_its_own_provenance(client, make_org, enabled_settings) -> None:
    user, project = make_org()
    _as(user)
    _refresh(client, project)

    summary = client.get(_url(project, "/summary")).json()

    assert summary["backlinks"] > 0
    assert summary["referring_domains"] > 0
    assert summary["authority"] is not None
    assert summary["last_import"]["vendor"] == "mock"
    assert summary["last_import"]["measurable"] is True
    assert summary["last_import"]["provenance"]["vendor"] == "mock"
    assert summary["velocity"], "one import is still a velocity series of one"
    assert summary["anchors"]["total"] > 0
    assert set(summary["toxicity"]) >= {"low", "medium", "high"}


def test_the_inventory_pages_and_reports_the_true_total(client, make_org, enabled_settings) -> None:
    user, project = make_org()
    _as(user)
    _refresh(client, project)

    page = client.get(_url(project), params={"limit": 2}).json()

    assert len(page["items"]) == 2
    assert page["total"] > 2, "the total must describe the filter, not the page"
    assert page["limit"] == 2


def test_the_inventory_filters_on_follow_and_anchor_class(
    client, make_org, enabled_settings
) -> None:
    user, project = make_org()
    _as(user)
    _refresh(client, project)

    nofollow = client.get(_url(project), params={"follow": False, "limit": 500}).json()
    everything = client.get(_url(project), params={"limit": 500}).json()

    assert nofollow["total"] < everything["total"]
    assert all(item["is_follow"] is False for item in nofollow["items"])

    brand = client.get(_url(project), params={"anchor_class": "brand", "limit": 500}).json()
    assert all(item["anchor_class"] == "brand" for item in brand["items"])


def test_referring_domains_carry_the_reasons_behind_a_toxicity_band(
    client, make_org, enabled_settings
) -> None:
    """A flag without its reasons is the credibility trap the plan calls out."""

    user, project = make_org()
    _as(user)
    _refresh(client, project)

    flagged = client.get(_url(project, "/referring-domains"), params={"band": "high"}).json()

    assert flagged["total"] > 0, "the mock fixture contains a deliberate link farm"
    for item in flagged["items"]:
        assert item["toxicity_band"] == "high"
        assert item["toxicity_reasons"], "a band without reasons must not ship"


def test_opportunities_label_which_source_each_row_came_from(
    client, make_org, enabled_settings
) -> None:
    user, project = make_org()
    _as(user)
    _refresh(client, project)

    body = client.get(_url(project, "/opportunities")).json()

    assert "link_gap" in body["provenance"]
    assert "no vendor call" in body["provenance"]["unlinked_mentions"]


# --------------------------------------------------------------------------
# Competitors — what makes gap analysis have an answer
# --------------------------------------------------------------------------


def test_tracking_a_competitor_is_idempotent(client, make_org, enabled_settings) -> None:
    user, project = make_org()
    _as(user)

    first = client.post(_url(project, "/competitors"), json={"domain": "https://rival.test/"})
    second = client.post(_url(project, "/competitors"), json={"domain": "rival.test"})

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["competitor_domain"] == "rival.test"

    listed = client.get(_url(project, "/competitors")).json()
    assert len(listed) == 1


def test_a_project_cannot_be_its_own_competitor(client, make_org, enabled_settings) -> None:
    user, project = make_org()
    _as(user)

    response = client.post(_url(project, "/competitors"), json={"domain": DOMAIN})

    assert response.status_code == 422


def test_untracking_a_competitor_removes_it(client, make_org, enabled_settings) -> None:
    user, project = make_org()
    _as(user)
    created = client.post(_url(project, "/competitors"), json={"domain": "rival.test"}).json()

    deleted = client.delete(_url(project, f"/competitors/{created['id']}"))

    assert deleted.status_code == 204
    assert client.get(_url(project, "/competitors")).json() == []


def test_a_viewer_may_not_track_a_competitor(client, make_org, enabled_settings) -> None:
    """Tracking one causes their profile to be pulled — it is a spending decision."""

    user, project = make_org(role="viewer")
    _as(user)

    response = client.post(_url(project, "/competitors"), json={"domain": "rival.test"})

    assert response.status_code == 403


# --------------------------------------------------------------------------
# Exports
# --------------------------------------------------------------------------


def test_the_csv_export_carries_a_header_and_the_rows(
    client, make_org, enabled_settings, db_session
) -> None:
    user, project = make_org()
    _as(user)
    _refresh(client, project)

    response = client.get(_url(project, "/export.csv"))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]

    lines = [line for line in response.text.splitlines() if line]
    assert lines[0].startswith("source_url,source_domain,target_url,anchor")
    live = db_session.scalar(
        sa.select(sa.func.count()).select_from(Backlink).where(Backlink.status == "active")
    )
    assert len(lines) - 1 == live


def test_the_disavow_export_carries_its_evidence(client, make_org, enabled_settings) -> None:
    user, project = make_org()
    _as(user)
    _refresh(client, project)

    response = client.get(_url(project, "/disavow.txt"))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "domain:" in response.text
    # Google's format allows comments, and the reasons ride along in them so the
    # evidence does not vanish the moment the file leaves the product.
    assert "#" in response.text
