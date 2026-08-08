"""Plan limits, enforced on the paths that spend money (P7.6, ADR-45).

Everything in ``services/billing`` shipped in session 21 and had no caller on
any path a customer touches for three sessions, so every organization was
silently on Free and Free meant nothing. This file is the proof that stopped
being true. It is organized by the question each test answers:

* does the allowance actually refuse the next one?
* is the refusal *distinguishable* from the other things that answer 429 and
  from a deployment fault?
* does a refused request leave nothing behind, and does a refusal by an earlier
  guard leave the allowance unspent?
* is a "stock" limit (projects) counted differently from a "flow" limit
  (analyses, audits), as a customer reading the plan would expect?
* does turning the kill switch off actually turn all of it off?
"""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import urlsplit

import pytest
import sqlalchemy as sa

from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import Analysis, CreditLedgerEntry, Plan, SeoProject, SiteAudit, UsageCounter
from app.services import billing

ANALYSES_URL = "/api/v1/analyses"
PROJECTS_URL = "/api/v1/seo-projects"
VALID_URL = "https://example.com"


def _pin_settings(**overrides) -> None:
    """Pin route settings, with this file's two standing choices baked in.

    ``site_audit_enabled=True`` because Site Audit is metered even though
    production runs it dark (ADR-44), and a quota only ever exercised with the
    feature off is a quota nobody has tested. The flag's own behaviour lives in
    ``test_seo_projects_api.py``.

    The per-IP limit is lifted out of the way because it and the plan quota both
    answer **429**, and both default to 5 — so on stock settings the sixth
    submit would be refused by whichever check runs first, and this file would
    be silently testing the rate limiter. ``test_rate_limit.py`` makes the
    mirror-image choice (unlimited plan, stock rate limit) for the same reason.
    """

    defaults: dict[str, object] = {
        "site_audit_enabled": True,
        "analyses_rate_limit_per_ip_hour": 1000,
        "analyses_daily_cap": 1000,
    }
    defaults.update(overrides)
    settings = Settings(**defaults)
    app.dependency_overrides[get_settings] = lambda: settings


@pytest.fixture(autouse=True)
def pinned_settings():
    _pin_settings()
    yield
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture(autouse=True)
def resolve_test_domains(monkeypatch):
    from app.api import seo_project_routes

    real_guard = seo_project_routes.is_public_url

    def guard(url: str) -> bool:
        host = urlsplit(url).hostname or ""
        return True if host.endswith(".test") else real_guard(url)

    monkeypatch.setattr(seo_project_routes, "is_public_url", guard)


def _submit(client, url: str = VALID_URL):
    return client.post(ANALYSES_URL, json={"url": url})


def _create_project(client, domain: str):
    return client.post(
        PROJECTS_URL,
        json={
            "domain": domain,
            "page_limit": 5,
            "profile_id": "site_audit_mobile",
            "js_rendering": False,
        },
    )


# --------------------------------------------------------------------------
# The allowance refuses the next one
# --------------------------------------------------------------------------


def test_free_allows_five_analyses_a_month_and_refuses_the_sixth(client, db_session, signed_in):
    _, org = signed_in()

    for n in range(5):
        assert _submit(client).status_code == 202, f"submit {n + 1} of 5"

    refused = _submit(client)
    assert refused.status_code == 429
    body = refused.json()
    assert body["metric"] == billing.METRIC_ANALYSES
    assert body["limit"] == 5
    assert body["used"] == 5

    # The refused one left nothing behind: no row, and no sixth tick.
    assert db_session.scalar(sa.select(sa.func.count()).select_from(Analysis)) == 5
    assert billing.usage(db_session, org.id, billing.METRIC_ANALYSES) == 5


def test_an_org_with_no_subscription_falls_back_to_free_rather_than_to_unlimited(
    client, db_session, signed_in
):
    """Every production organization is in exactly this state — no subscription
    row was ever created — so the fallback direction is not a corner case, it is
    the default for every customer."""

    _, org = signed_in()
    assert billing.plan_for_org(db_session, org.id) is None
    assert billing.limit_for(db_session, org.id, billing.METRIC_ANALYSES) == 5


def test_moving_up_a_tier_lifts_the_ceiling_without_resetting_the_counter(
    client, db_session, signed_in, on_plan
):
    """What the operator's `set_org_plan.py` has to accomplish: room, now,
    without wiping the month's usage — a tier change is not an amnesty."""

    _, org = signed_in()
    for _ in range(5):
        assert _submit(client).status_code == 202
    assert _submit(client).status_code == 429

    on_plan(org.id, "starter")

    assert _submit(client).status_code == 202
    assert billing.usage(db_session, org.id, billing.METRIC_ANALYSES) == 6


def test_an_unlimited_plan_never_refuses(client, signed_in):
    _, org = signed_in(plan_key="enterprise")
    for _ in range(7):  # comfortably past every finite tier's Free allowance
        assert _submit(client).status_code == 202


# --------------------------------------------------------------------------
# Telling the three refusals apart
# --------------------------------------------------------------------------


def test_a_quota_429_is_distinguishable_from_a_rate_limit_429(client, signed_in):
    """Both are 429 and they ask the customer to do opposite things: one is
    "wait a moment", the other is "this will not change until next month".
    A client that cannot tell them apart gives the wrong advice half the time."""

    signed_in(plan_key="enterprise")
    _pin_settings(analyses_rate_limit_per_ip_hour=0)

    throttled = _submit(client)
    assert throttled.status_code == 429
    assert throttled.headers.get("Retry-After") is not None
    assert "limit" not in throttled.json()


def test_an_unseeded_catalog_is_a_503_not_a_429(client, db_session, signed_in):
    """A deployment whose `plans` table never got seeded must not tell every
    organization at once that it is out of quota. Production ran with an empty
    catalog until session 21 caught it; enforced quotas would have turned that
    into a total outage wearing a customer-error costume."""

    signed_in()
    db_session.execute(sa.delete(Plan))
    db_session.commit()

    response = _submit(client)
    assert response.status_code == 503
    assert "plans are not configured" in response.json()["detail"]


# --------------------------------------------------------------------------
# Ordering: an earlier refusal must not spend the allowance
# --------------------------------------------------------------------------


def test_an_ssrf_rejection_costs_no_quota(client, db_session, signed_in):
    _, org = signed_in()

    for _ in range(10):
        assert _submit(client, "http://127.0.0.1/").status_code == 422

    assert billing.usage(db_session, org.id, billing.METRIC_ANALYSES) == 0
    assert _submit(client).status_code == 202


def test_a_rate_limited_submit_costs_no_quota(client, db_session, signed_in):
    """The two guards are ordered, and the order matters in one direction only:
    a burst that the IP limit refuses must not also eat a month's allowance."""

    _, org = signed_in()
    _pin_settings(analyses_rate_limit_per_ip_hour=0)

    assert _submit(client).status_code == 429
    assert billing.usage(db_session, org.id, billing.METRIC_ANALYSES) == 0


def test_a_409_after_the_meter_ran_gives_the_allowance_back(
    client, db_session, signed_in, on_plan
):
    """The counter and the thing it pays for commit together, or neither does.

    `create_site_audit` meters *before* `queue_site_audit`, which is the only
    order that can refuse before work starts — so the 409 for an already-running
    crawl lands after the increment. Nothing commits, so the transaction closes
    and takes the increment with it. If `consume_quota` ever grew its own
    commit, this test is what would notice.
    """

    _, org = signed_in()
    on_plan(org.id, "starter")

    project = _create_project(client, "busy.test")
    assert project.status_code == 201
    assert billing.usage(db_session, org.id, billing.METRIC_SITE_AUDITS) == 1

    # The first crawl is still queued, so a second is a 409.
    conflict = client.post(f"{PROJECTS_URL}/{project.json()['id']}/audits", json={})
    assert conflict.status_code == 409
    assert billing.usage(db_session, org.id, billing.METRIC_SITE_AUDITS) == 1


def test_a_refused_analysis_writes_no_row_and_no_audit_event(client, db_session, signed_in):
    from app.db.models import AuditEvent

    signed_in()
    for _ in range(5):
        assert _submit(client).status_code == 202
    before = db_session.scalar(
        sa.select(sa.func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.action == "analysis:create")
    )

    assert _submit(client).status_code == 429

    after = db_session.scalar(
        sa.select(sa.func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.action == "analysis:create")
    )
    assert after == before == 5


# --------------------------------------------------------------------------
# Stock vs flow
# --------------------------------------------------------------------------


def test_projects_are_a_stock_so_the_limit_is_what_you_hold_not_what_you_made(
    client, db_session, signed_in
):
    """Free says "1 project". A customer reads that as one at a time.

    A monthly counter would read it as one *per month* — twelve by December,
    and deleting one would free nothing back. So the check counts rows.

    Site Audit is switched off here — its production default — so the only
    allowance in play is the project one. With crawls on, Free's single monthly
    audit would run out first and this test would be proving the wrong limit.
    """

    _, org = signed_in()
    _pin_settings(site_audit_enabled=False)

    assert _create_project(client, "first.test").status_code == 201
    refused = _create_project(client, "second.test")
    assert refused.status_code == 429
    assert refused.json()["metric"] == billing.METRIC_PROJECTS

    # No monthly counter was ever ticked for projects — the rows are the count.
    assert (
        db_session.scalar(
            sa.select(sa.func.count())
            .select_from(UsageCounter)
            .where(UsageCounter.metric == billing.METRIC_PROJECTS)
        )
        == 0
    )

    # Deleting the project frees the slot immediately, which a monthly counter
    # could not do.
    db_session.execute(sa.delete(SiteAudit))
    db_session.execute(sa.delete(SeoProject))
    db_session.commit()
    assert _create_project(client, "third.test").status_code == 201


def test_a_duplicate_domain_is_409_even_when_the_plan_is_full(client, signed_in):
    """Both refusals are true at once on Free, and only one of them is useful:
    a 429 would tell the customer to buy capacity for a project they already
    have."""

    signed_in()
    assert _create_project(client, "only.test").status_code == 201
    assert _create_project(client, "only.test").status_code == 409


def test_site_audits_are_a_monthly_flow(client, db_session, signed_in, on_plan):
    _, org = signed_in()
    on_plan(org.id, "starter")  # 3 projects, 20 audits

    project = _create_project(client, "audited.test")
    assert project.status_code == 201
    assert billing.usage(db_session, org.id, billing.METRIC_SITE_AUDITS) == 1

    # Finish the first crawl so a rerun is allowed, then prove the rerun meters.
    audit = db_session.scalar(sa.select(SiteAudit))
    assert audit is not None
    audit.status = "done"
    db_session.commit()

    rerun = client.post(f"{PROJECTS_URL}/{project.json()['id']}/audits", json={})
    assert rerun.status_code == 202
    assert billing.usage(db_session, org.id, billing.METRIC_SITE_AUDITS) == 2


def test_a_crawl_that_is_never_queued_is_never_metered(client, db_session, signed_in):
    """SITE_AUDIT_ENABLED is off in production (ADR-44), so project creation
    queues no crawl. Charging for the crawl anyway would bill for work that
    provably cannot happen."""

    _, org = signed_in()
    _pin_settings(site_audit_enabled=False)

    assert _create_project(client, "dark.test").status_code == 201
    assert db_session.scalar(sa.select(sa.func.count()).select_from(SiteAudit)) == 0
    assert billing.usage(db_session, org.id, billing.METRIC_SITE_AUDITS) == 0


def test_another_tenants_project_id_never_spends_your_allowance(
    client, db_session, signed_in, on_plan
):
    """A 404 for someone else's project must cost the caller nothing — otherwise
    a stranger's ids are a way to drain an organization's month."""

    _, victim_org = signed_in(email="victim@example.test")
    project = _create_project(client, "victim.test")
    assert project.status_code == 201
    project_id = project.json()["id"]

    _, attacker_org = signed_in(email="attacker@example.test")
    on_plan(attacker_org.id, "starter")
    for _ in range(5):
        assert client.post(f"{PROJECTS_URL}/{project_id}/audits", json={}).status_code == 404

    assert billing.usage(db_session, attacker_org.id, billing.METRIC_SITE_AUDITS) == 0


# --------------------------------------------------------------------------
# The kill switch
# --------------------------------------------------------------------------


def test_the_kill_switch_turns_all_of_it_off(client, db_session, signed_in):
    """One flag, one behaviour. Half-enforcement — some paths metered, others
    not — would be worse than either state, because the numbers would look real
    and be wrong."""

    _, org = signed_in()
    _pin_settings(quota_enforcement_enabled=False)

    for _ in range(8):  # well past Free's 5
        assert _submit(client).status_code == 202
    assert _create_project(client, "one.test").status_code == 201
    assert _create_project(client, "two.test").status_code == 201

    # And nothing was counted, so flipping the switch back on does not
    # immediately refuse everyone for a month they did not knowingly spend.
    assert billing.usage(db_session, org.id, billing.METRIC_ANALYSES) == 0


# --------------------------------------------------------------------------
# Spend reaches the ledger
# --------------------------------------------------------------------------


def test_a_finished_run_settles_its_real_cost_against_the_org(db_session, signed_in, settings):
    """Counts gate; money is recorded. The credit ledger is where per-org spend
    becomes visible for the first time — the input A8's spend rollups need."""

    from app.db.models import Prompt, Response
    from app.worker import _settle

    _, org = signed_in()
    analysis = Analysis(url=VALID_URL, org_id=org.id, status="done")
    db_session.add(analysis)
    db_session.flush()
    prompt = Prompt(analysis_id=analysis.id, text="q", category="discovery")
    db_session.add(prompt)
    db_session.flush()
    db_session.add(
        Response(
            analysis_id=analysis.id,
            prompt_id=prompt.id,
            engine="mock",
            model="mock-1",
            raw_text="a",
            cost_usd=Decimal("0.0250"),
        )
    )
    db_session.commit()

    _settle(db_session, analysis)

    entries = list(db_session.scalars(sa.select(CreditLedgerEntry)))
    assert len(entries) == 1
    assert entries[0].org_id == org.id
    assert entries[0].delta_usd == Decimal("-0.025000")
    assert entries[0].source_id == analysis.id

    # Idempotent: the worker retries a job up to MAX_ATTEMPTS.
    _settle(db_session, analysis)
    assert db_session.scalar(sa.select(sa.func.count()).select_from(CreditLedgerEntry)) == 1


def test_a_failed_run_still_records_what_it_spent(db_session, signed_in):
    """A run that died in step five still paid for steps one to four. A ledger
    that records only successes understates spend in the direction that hides
    a problem (ADR-34's lesson)."""

    from app.db.models import Prompt, Response
    from app.worker import _settle

    _, org = signed_in()
    analysis = Analysis(url=VALID_URL, org_id=org.id, status="failed", error="boom")
    db_session.add(analysis)
    db_session.flush()
    prompt = Prompt(analysis_id=analysis.id, text="q", category="discovery")
    db_session.add(prompt)
    db_session.flush()
    db_session.add(
        Response(
            analysis_id=analysis.id,
            prompt_id=prompt.id,
            engine="mock",
            model="mock-1",
            raw_text="a",
            cost_usd=Decimal("0.0100"),
        )
    )
    db_session.commit()

    _settle(db_session, analysis)

    entry = db_session.scalar(sa.select(CreditLedgerEntry))
    assert entry is not None
    assert entry.delta_usd == Decimal("-0.010000")
    assert entry.detail["status"] == "failed"


def test_a_zero_cost_run_still_writes_a_row(db_session, signed_in):
    """"This ran and cost nothing" and "this never ran" are different facts, and
    the ledger is where the difference is visible — which is also what makes the
    DRY_RUN suite's $0 assertions mean anything."""

    from app.worker import _settle

    _, org = signed_in()
    analysis = Analysis(url=VALID_URL, org_id=org.id, status="done")
    db_session.add(analysis)
    db_session.commit()

    _settle(db_session, analysis)

    entry = db_session.scalar(sa.select(CreditLedgerEntry))
    assert entry is not None
    assert entry.delta_usd == Decimal("0")

    _settle(db_session, analysis)
    assert db_session.scalar(sa.select(sa.func.count()).select_from(CreditLedgerEntry)) == 1


def test_an_organization_less_run_is_not_charged_to_anyone(db_session):
    """Checker runs and every pre-P7.6 row have no organization. Inventing one
    to make the ledger tidy would be worse than the gap."""

    from app.worker import _settle

    analysis = Analysis(url=VALID_URL, status="done")
    db_session.add(analysis)
    db_session.commit()

    assert _settle(db_session, analysis) is None
    assert db_session.scalar(sa.select(sa.func.count()).select_from(CreditLedgerEntry)) == 0
