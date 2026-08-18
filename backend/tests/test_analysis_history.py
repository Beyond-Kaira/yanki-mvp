"""`GET /api/v1/analyses` — the organization's own history (tech-debt #77).

Runs have carried an `org_id` since P7.6 and there was no way to list them: the
only route to a result was the URL you were redirected to, so closing the tab
lost it. The data existed and the screen did not.

The interesting cases here are not "does it return rows". They are the three
places this route could quietly be wrong:

* **Whose rows.** It is the first application call site of `tenancy.scoped()`,
  the fail-closed helper that had none (tech-debt #63) — so the tests that
  matter most are the ones asserting another tenant's run is absent, and that a
  context without an organization raises rather than returning everything.
* **Which rows.** Pre-P7.6 runs carry no `org_id` and belong to nobody;
  anonymous checker runs are in the same table. Neither may appear in a
  customer's history, and they are excluded by two different mechanisms.
* **How many rows.** A page that repeats one run and skips another is the
  classic unstable-pagination bug, and it is invisible until a customer is
  looking for a run that the list will never show them.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import Analysis
from app.services.analyses import list_org_analyses
from app.services.tenancy import OrgContext, OrgScopeRequired

ANALYSES_URL = "/api/v1/analyses"


@pytest.fixture(autouse=True)
def unmetered():
    """These tests are about the list, not the quota. Free allows five runs a
    month and several cases here need more than five rows, so the plan is lifted
    out of the way rather than worked around with sleeps or fake clocks."""

    app.dependency_overrides[get_settings] = lambda: Settings(
        analyses_rate_limit_per_ip_hour=1000,
        analyses_daily_cap=1000,
        quota_enforcement_enabled=False,
    )
    yield
    app.dependency_overrides.pop(get_settings, None)


def _seed(
    session: Session,
    *,
    org_id: uuid.UUID | None,
    created_by_user_id: uuid.UUID | None = None,
    count: int = 1,
    **kwargs,
) -> list[Analysis]:
    rows = []
    for index in range(count):
        row = Analysis(
            url=f"https://example.com/{uuid.uuid4().hex[:8]}/{index}",
            org_id=org_id,
            created_by_user_id=created_by_user_id,
            **kwargs,
        )
        session.add(row)
        rows.append(row)
    session.commit()
    return rows


# ---------------------------------------------------------------------------
# Whose rows
# ---------------------------------------------------------------------------


def test_the_history_lists_this_organizations_runs(client, db_session, signed_in) -> None:
    user, org = signed_in()
    _seed(db_session, org_id=org.id, created_by_user_id=user.id, count=3)

    response = client.get(ANALYSES_URL)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    assert len(body["analyses"]) == 3


def test_another_tenants_runs_are_absent(client, db_session, signed_in) -> None:
    """The leakage case. Not a 403 or an error — simply not there, which is what
    org scoping means when it works."""

    user, org = signed_in()
    _seed(db_session, org_id=org.id, created_by_user_id=user.id, count=2)
    _seed(db_session, org_id=uuid.uuid4(), created_by_user_id=uuid.uuid4(), count=5)

    body = client.get(ANALYSES_URL).json()

    assert body["total"] == 2
    assert len(body["analyses"]) == 2


def test_a_context_with_no_organization_raises_rather_than_listing_everything(
    db_session: Session,
) -> None:
    """`scoped()` fails closed, and this is the property that makes it worth
    using over a hand-written `where`: the org-less case is an exception, not a
    query that quietly returns every tenant's rows."""

    _seed(db_session, org_id=uuid.uuid4(), count=3)

    with pytest.raises(OrgScopeRequired):
        list_org_analyses(db_session, OrgContext.public())


def test_a_system_context_deliberately_sees_across_organizations(db_session: Session) -> None:
    """The opt-out is explicit and belongs to workers and platform paths. Pinned
    because it is a real bypass: if it ever became reachable from a request it
    would be the leak, so its shape should be visible in a test rather than only
    in `scoped`'s docstring."""

    _seed(db_session, org_id=uuid.uuid4(), count=2)
    _seed(db_session, org_id=uuid.uuid4(), count=3)

    page = list_org_analyses(db_session, OrgContext.system())

    assert page.total == 5


def test_the_route_refuses_an_anonymous_caller(client, db_session) -> None:
    """There is no id to hold, so there is no capability to honour. Unlike the
    detail route, an unauthenticated version of this one could only mean
    "everyone's analyses"."""

    _seed(db_session, org_id=uuid.uuid4(), count=2)

    assert client.get(ANALYSES_URL).status_code == 401


# ---------------------------------------------------------------------------
# Which rows
# ---------------------------------------------------------------------------


def test_runs_from_before_the_tenancy_change_belong_to_nobody(
    client, db_session, signed_in
) -> None:
    """Every analysis in production today has `org_id IS NULL`. They are still
    readable by id — that capability is untouched — and they appear in no
    organization's history, because inventing an owner for them would be a worse
    answer than omitting them."""

    user, org = signed_in()
    _seed(db_session, org_id=None, count=4)
    _seed(db_session, org_id=org.id, created_by_user_id=user.id, count=1)

    body = client.get(ANALYSES_URL).json()

    assert body["total"] == 1


def test_a_checker_run_never_appears_in_an_organizations_history(
    client, db_session, signed_in
) -> None:
    """Two independent reasons, which is the point: checker runs are anonymous
    (no `org_id`, so scoping excludes them) *and* `kind='checker'` is outside
    `LISTABLE_KINDS`. If the anonymous funnel ever gained an organization, the
    second reason would still hold."""

    user, org = signed_in()
    db_session.add(
        Analysis(url="checker://acme/widgets", kind="checker", brand="acme", org_id=org.id)
    )
    db_session.commit()
    _seed(db_session, org_id=org.id, created_by_user_id=user.id, count=1)

    body = client.get(ANALYSES_URL).json()

    assert body["total"] == 1
    assert not any(row["url"].startswith("checker://") for row in body["analyses"])


def test_status_narrows_the_list_and_the_total_together(client, db_session, signed_in) -> None:
    """The total is computed over the filtered statement, so "1–20 of 3" means
    what a reader assumes. A total taken from the unfiltered table is the bug
    that makes a paginator offer pages that are always empty."""

    user, org = signed_in()
    _seed(db_session, org_id=org.id, created_by_user_id=user.id, count=2, status="done")
    _seed(db_session, org_id=org.id, created_by_user_id=user.id, count=3, status="failed")

    body = client.get(ANALYSES_URL, params={"status": "done"}).json()

    assert body["total"] == 2
    assert {row["status"] for row in body["analyses"]} == {"done"}


# ---------------------------------------------------------------------------
# How many rows
# ---------------------------------------------------------------------------


def test_paging_never_repeats_or_skips_a_run(client, db_session, signed_in) -> None:
    """The unstable-pagination guard. Rows seeded in one transaction share a
    `created_at` to microsecond precision, which is exactly the case where a
    sort without a tiebreaker lets page 2 repeat a row from page 1 and drop
    another — and a customer hunting for a missing run would never find it."""

    user, org = signed_in()
    _seed(db_session, org_id=org.id, created_by_user_id=user.id, count=7)

    first = client.get(ANALYSES_URL, params={"limit": 3, "offset": 0}).json()
    second = client.get(ANALYSES_URL, params={"limit": 3, "offset": 3}).json()
    third = client.get(ANALYSES_URL, params={"limit": 3, "offset": 6}).json()

    seen = [row["id"] for page in (first, second, third) for row in page["analyses"]]
    assert len(seen) == 7
    assert len(set(seen)) == 7
    assert first["total"] == 7


def test_the_page_size_is_bounded(client, db_session, signed_in) -> None:
    """An unbounded `limit` on a table that grows forever is a self-inflicted
    denial of service. Refused at the schema, so it never reaches the query."""

    _user, _org = signed_in()

    assert client.get(ANALYSES_URL, params={"limit": 5000}).status_code == 422
    assert client.get(ANALYSES_URL, params={"limit": 0}).status_code == 422
    assert client.get(ANALYSES_URL, params={"offset": -1}).status_code == 422


def test_newest_first(client, db_session, signed_in) -> None:
    user, org = signed_in()
    _seed(db_session, org_id=org.id, created_by_user_id=user.id, count=5)

    body = client.get(ANALYSES_URL).json()
    timestamps = [row["created_at"] for row in body["analyses"]]

    assert timestamps == sorted(timestamps, reverse=True)


# ---------------------------------------------------------------------------
# What a row says
# ---------------------------------------------------------------------------


def test_an_unfinished_run_reports_a_null_score_not_a_zero(client, db_session, signed_in) -> None:
    """ "We have not measured this yet" and "this scored zero" are different
    facts, and the second is far worse news. The API must not conflate them —
    the UI renders null as an em dash and can only do that if null arrives."""

    user, org = signed_in()
    _seed(db_session, org_id=org.id, created_by_user_id=user.id, count=1, status="queued")

    row = client.get(ANALYSES_URL).json()["analyses"][0]

    assert row["status"] == "queued"
    assert row["geo_score"] is None


def test_a_summary_row_carries_no_result_envelope(client, db_session, signed_in) -> None:
    """A finished run holds dozens of responses. Serializing the full envelope
    for every row would make a twenty-row page thousands of records deep, to
    render a table of URLs and scores. The detail route is one click away."""

    user, org = signed_in()
    _seed(
        db_session,
        org_id=org.id,
        created_by_user_id=user.id,
        count=1,
        status="done",
        geo_score=61.5,
    )

    row = client.get(ANALYSES_URL).json()["analyses"][0]

    assert row["geo_score"] == 61.5
    assert "result" not in row
    assert "responses" not in row


def test_an_empty_history_is_an_empty_page_not_an_error(client, signed_in) -> None:
    _user, _org = signed_in()

    body = client.get(ANALYSES_URL).json()

    assert body == {
        "total": 0,
        "limit": 20,
        "offset": 0,
        "analyses": [],
        "user_analyses_used": 0,
        "user_analyses_limit": 5,
    }


def test_a_teammates_run_is_absent_from_my_history(client, db_session, signed_in) -> None:
    """User scoping within one organization. Org membership alone does not share
    analysis history — each person sees only what they queued."""

    from app.db.models import Membership, User
    from app.services.auth import hash_password

    owner, org = signed_in(email="owner@example.test")
    teammate = User(email="teammate@example.test", password_hash=hash_password("correct-horse"))
    db_session.add(teammate)
    db_session.flush()
    db_session.add(Membership(org_id=org.id, user_id=teammate.id, role="viewer", status="active"))
    _seed(db_session, org_id=org.id, created_by_user_id=teammate.id, count=2)
    _seed(db_session, org_id=org.id, created_by_user_id=owner.id, count=1)

    body = client.get(ANALYSES_URL).json()

    assert body["total"] == 1
    assert len(body["analyses"]) == 1


def test_a_teammates_run_returns_404_on_detail(client, db_session, signed_in) -> None:
    from app.db.models import Membership, User
    from app.services.auth import hash_password

    owner, org = signed_in(email="owner@example.test")
    teammate = User(email="teammate@example.test", password_hash=hash_password("correct-horse"))
    db_session.add(teammate)
    db_session.flush()
    db_session.add(Membership(org_id=org.id, user_id=teammate.id, role="viewer", status="active"))
    rows = _seed(db_session, org_id=org.id, created_by_user_id=teammate.id, count=1, status="done")
    theirs = rows[0].id

    assert client.get(f"/api/v1/analyses/{theirs}").status_code == 404


def test_legacy_org_rows_without_a_creator_stay_out_of_history(
    client, db_session, signed_in
) -> None:
    user, org = signed_in()
    _seed(db_session, org_id=org.id, created_by_user_id=None, count=3, status="done")
    _seed(db_session, org_id=org.id, created_by_user_id=user.id, count=1)

    body = client.get(ANALYSES_URL).json()

    assert body["total"] == 1
