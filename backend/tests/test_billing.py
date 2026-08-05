"""Quotas and the credit ledger (P7.6) — the layer that makes spend real.

The tests that matter here are about the two ways a metering layer lies:

* **Silently allowing spend** — an unknown plan defaulting to unlimited, a
  quota check that can be run without the increment, a reservation that admits
  more than the balance covers.
* **Silently losing spend** — a $0 charge skipped rather than recorded, a
  charge refused after the money was already gone, a balance that drifts from
  the sum of its entries.

Both are represented below, and the second set is the one that would have
caught ADR-34's week of $0 analyses.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.db.models import CreditLedgerEntry, Organization, Plan, Subscription
from app.services import billing
from app.services.billing import (
    METRIC_ANALYSES,
    METRIC_BACKLINK_REFRESHES,
    InsufficientCredit,
    QuotaExceeded,
)


@pytest.fixture()
def org(db_session):
    org = Organization(name="Acme", slug="acme", kind="company")
    db_session.add(org)
    db_session.flush()
    billing.seed_plans(db_session)
    db_session.commit()
    return org


def _subscribe(db_session, org, plan_key: str):
    plan = db_session.scalar(sa.select(Plan).where(Plan.key == plan_key))
    db_session.add(Subscription(org_id=org.id, plan_id=plan.id, status="active"))
    db_session.commit()
    return plan


# --------------------------------------------------------------------------
# The catalog
# --------------------------------------------------------------------------


def test_seeding_is_idempotent(db_session, org):
    before = db_session.scalar(sa.select(sa.func.count()).select_from(Plan))
    assert billing.seed_plans(db_session) == 0
    db_session.commit()
    assert db_session.scalar(sa.select(sa.func.count()).select_from(Plan)) == before


def test_every_plan_declares_every_metric(db_session, org):
    """A metric missing from a plan is a seeding bug that would read as unlimited."""

    for plan in db_session.scalars(sa.select(Plan)):
        for metric in (METRIC_ANALYSES, METRIC_BACKLINK_REFRESHES):
            assert metric in plan.limits, f"{plan.key} does not declare {metric}"


def test_unlimited_and_unavailable_are_different_values(db_session, org):
    """None means unlimited; 0 means not on this plan. Conflating them is a bug."""

    free = db_session.scalar(sa.select(Plan).where(Plan.key == "free"))
    enterprise = db_session.scalar(sa.select(Plan).where(Plan.key == "enterprise"))
    assert free.limits[METRIC_BACKLINK_REFRESHES] == 0
    assert enterprise.limits[METRIC_BACKLINK_REFRESHES] is None


# --------------------------------------------------------------------------
# Quotas
# --------------------------------------------------------------------------


def test_an_org_with_no_subscription_falls_back_to_free_not_unlimited(db_session, org):
    """The direction matters: unlimited-by-default makes every misconfig free spend."""

    assert billing.limit_for(db_session, org.id, METRIC_ANALYSES) == 5


def test_quota_is_enforced_at_the_limit(db_session, org):
    _subscribe(db_session, org, "free")
    for _ in range(5):
        billing.consume_quota(db_session, org.id, METRIC_ANALYSES)
    db_session.commit()

    with pytest.raises(QuotaExceeded) as excinfo:
        billing.consume_quota(db_session, org.id, METRIC_ANALYSES)
    assert excinfo.value.metric == METRIC_ANALYSES
    assert excinfo.value.used == 5
    assert excinfo.value.limit == 5


def test_a_zero_limit_refuses_the_first_use(db_session, org):
    _subscribe(db_session, org, "free")
    with pytest.raises(QuotaExceeded):
        billing.consume_quota(db_session, org.id, METRIC_BACKLINK_REFRESHES)


def test_unlimited_never_refuses(db_session, org):
    _subscribe(db_session, org, "enterprise")
    for _ in range(50):
        billing.consume_quota(db_session, org.id, METRIC_ANALYSES)
    db_session.commit()
    assert billing.usage(db_session, org.id, METRIC_ANALYSES) == 50


def test_usage_is_windowed_by_calendar_month(db_session, org):
    _subscribe(db_session, org, "starter")
    january = datetime(2026, 1, 15, tzinfo=UTC)
    february = datetime(2026, 2, 2, tzinfo=UTC)

    billing.consume_quota(db_session, org.id, METRIC_ANALYSES, now=january)
    db_session.commit()

    assert billing.usage(db_session, org.id, METRIC_ANALYSES, now=january) == 1
    assert billing.usage(db_session, org.id, METRIC_ANALYSES, now=february) == 0


def test_quota_is_per_org(db_session, org):
    _subscribe(db_session, org, "free")
    other = Organization(name="Other", slug="other", kind="company")
    db_session.add(other)
    db_session.commit()

    for _ in range(5):
        billing.consume_quota(db_session, org.id, METRIC_ANALYSES)
    db_session.commit()

    # The other org's allowance is untouched.
    billing.consume_quota(db_session, other.id, METRIC_ANALYSES)
    db_session.commit()
    assert billing.usage(db_session, other.id, METRIC_ANALYSES) == 1


# --------------------------------------------------------------------------
# The ledger
# --------------------------------------------------------------------------


def test_a_new_org_has_no_balance(db_session, org):
    assert billing.balance(db_session, org.id) == Decimal("0")


def test_grants_and_charges_are_signed(db_session, org):
    billing.grant_credit(db_session, org.id, Decimal("10"))
    billing.record_charge(db_session, org.id, Decimal("2.5"), reason="analysis")
    db_session.commit()

    entries = db_session.scalars(sa.select(CreditLedgerEntry)).all()
    assert [e.delta_usd for e in entries] == [Decimal("10.000000"), Decimal("-2.500000")]
    assert billing.balance(db_session, org.id) == Decimal("7.5")


def test_a_charge_is_recorded_as_negative_however_it_is_passed(db_session, org):
    """Callers pass a cost, not a sign — a positive argument must still debit."""

    billing.grant_credit(db_session, org.id, Decimal("10"))
    billing.record_charge(db_session, org.id, Decimal("3"), reason="analysis")
    billing.record_charge(db_session, org.id, Decimal("-3"), reason="analysis")
    db_session.commit()
    assert billing.balance(db_session, org.id) == Decimal("4")


def test_balance_after_tracks_the_running_sum(db_session, org):
    billing.grant_credit(db_session, org.id, Decimal("10"))
    billing.record_charge(db_session, org.id, Decimal("4"), reason="analysis")
    db_session.commit()

    entries = db_session.scalars(
        sa.select(CreditLedgerEntry).order_by(CreditLedgerEntry.created_at)
    ).all()
    assert entries[-1].balance_after_usd == billing.balance(db_session, org.id)


def test_the_ledger_is_append_only_in_practice(db_session, org):
    """Correcting a charge means reversing it — both stay visible."""

    billing.grant_credit(db_session, org.id, Decimal("10"))
    billing.record_charge(db_session, org.id, Decimal("5"), reason="analysis")
    billing.grant_credit(db_session, org.id, Decimal("5"), reason="reversal:analysis")
    db_session.commit()

    assert billing.balance(db_session, org.id) == Decimal("10")
    assert db_session.scalar(sa.select(sa.func.count()).select_from(CreditLedgerEntry)) == 3


def test_a_real_charge_is_recorded_even_when_it_overdraws(db_session, org):
    """The money is already gone. Refusing to record it makes the ledger fiction."""

    billing.record_charge(db_session, org.id, Decimal("7"), reason="analysis")
    db_session.commit()
    assert billing.balance(db_session, org.id) == Decimal("-7")


def test_a_charge_can_be_refused_when_explicitly_asked_to_be(db_session, org):
    with pytest.raises(InsufficientCredit):
        billing.record_charge(
            db_session, org.id, Decimal("7"), reason="analysis", allow_negative=False
        )


# --------------------------------------------------------------------------
# Reserve → settle, the shape that stops invisible spend
# --------------------------------------------------------------------------


def test_a_reservation_takes_quota_and_checks_affordability(db_session, org):
    _subscribe(db_session, org, "starter")
    billing.grant_credit(db_session, org.id, Decimal("10"))
    db_session.commit()

    reservation = billing.reserve(
        db_session, org.id, metric=METRIC_ANALYSES, estimate_usd=Decimal("1")
    )
    db_session.commit()

    assert reservation.estimate_usd == Decimal("1")
    assert billing.usage(db_session, org.id, METRIC_ANALYSES) == 1
    # Nothing charged yet — the call has not been made.
    assert billing.balance(db_session, org.id) == Decimal("10")


def test_a_reservation_is_refused_before_any_money_moves(db_session, org):
    _subscribe(db_session, org, "starter")
    with pytest.raises(InsufficientCredit):
        billing.reserve(db_session, org.id, metric=METRIC_ANALYSES, estimate_usd=Decimal("5"))
    db_session.commit()
    assert billing.balance(db_session, org.id) == Decimal("0")


def test_a_reservation_is_refused_when_the_quota_is_gone(db_session, org):
    _subscribe(db_session, org, "free")
    billing.grant_credit(db_session, org.id, Decimal("100"))
    for _ in range(5):
        billing.consume_quota(db_session, org.id, METRIC_ANALYSES)
    db_session.commit()

    with pytest.raises(QuotaExceeded):
        billing.reserve(db_session, org.id, metric=METRIC_ANALYSES, estimate_usd=Decimal("1"))


def test_settling_records_the_actual_not_the_estimate(db_session, org):
    _subscribe(db_session, org, "starter")
    billing.grant_credit(db_session, org.id, Decimal("10"))
    reservation = billing.reserve(
        db_session, org.id, metric=METRIC_ANALYSES, estimate_usd=Decimal("2")
    )
    billing.settle(db_session, reservation, Decimal("0.35"))
    db_session.commit()

    assert billing.balance(db_session, org.id) == Decimal("9.65")
    entry = db_session.scalars(
        sa.select(CreditLedgerEntry).order_by(CreditLedgerEntry.created_at.desc())
    ).first()
    assert entry.detail["estimate_usd"] == "2"


def test_a_zero_cost_settle_still_writes_a_row(db_session, org):
    """'Ran and cost nothing' and 'never ran' are different facts.

    This is the property that makes the DRY_RUN suite's $0 assertions mean
    something — and the one whose absence hid a week of unrecorded spend
    (ADR-34).
    """

    _subscribe(db_session, org, "starter")
    billing.grant_credit(db_session, org.id, Decimal("10"))
    reservation = billing.reserve(
        db_session, org.id, metric=METRIC_ANALYSES, estimate_usd=Decimal("0")
    )
    entry = billing.settle(db_session, reservation, Decimal("0"))
    db_session.commit()

    assert entry is not None
    assert entry.delta_usd == Decimal("0")
    assert billing.balance(db_session, org.id) == Decimal("10")


def test_settle_carries_the_source_so_a_charge_traces_back(db_session, org):
    _subscribe(db_session, org, "starter")
    billing.grant_credit(db_session, org.id, Decimal("10"))
    reservation = billing.reserve(
        db_session, org.id, metric=METRIC_ANALYSES, estimate_usd=Decimal("1")
    )
    source = uuid.uuid4()
    entry = billing.settle(
        db_session, reservation, Decimal("0.5"), source_type="analysis", source_id=source
    )
    db_session.commit()

    assert entry.source_type == "analysis"
    assert entry.source_id == source


def test_ledgers_do_not_bleed_between_orgs(db_session, org):
    other = Organization(name="Other", slug="other", kind="company")
    db_session.add(other)
    db_session.commit()

    billing.grant_credit(db_session, org.id, Decimal("10"))
    db_session.commit()

    assert billing.balance(db_session, org.id) == Decimal("10")
    assert billing.balance(db_session, other.id) == Decimal("0")


# --------------------------------------------------------------------------
# The catalog must never be empty in a deployed database
# --------------------------------------------------------------------------


def test_an_empty_catalog_refuses_everything(db_session):
    """Why migration 0016 exists.

    `limit_for` falls back to Free rather than to unlimited, on purpose — an
    unknown plan defaulting to unlimited would make every misconfiguration a
    free-spend bug. But with no Free row to fall back TO, the fallback returns
    0, which reads as "you may do none of this". Fail-closed is the right
    direction and a total refusal is still an outage, which is why the catalog
    is seeded by a migration rather than left to a startup hook that nothing
    calls. Production ran with `plans` empty until this was caught.
    """

    from app.db.models import Organization

    org = Organization(name="Empty", slug="empty-catalog", kind="company")
    db_session.add(org)
    db_session.commit()

    # No plans seeded at all.
    assert db_session.scalar(sa.select(sa.func.count()).select_from(Plan)) == 0
    assert billing.limit_for(db_session, org.id, METRIC_ANALYSES) == 0

    with pytest.raises(QuotaExceeded):
        billing.consume_quota(db_session, org.id, METRIC_ANALYSES)


def test_the_seeded_catalog_covers_every_metric_the_code_meters(db_session):
    """A metric the code checks but no plan declares would read as unlimited."""

    billing.seed_plans(db_session)
    db_session.commit()

    metered = {
        billing.METRIC_ANALYSES,
        billing.METRIC_SITE_AUDITS,
        billing.METRIC_BACKLINK_REFRESHES,
        billing.METRIC_PROJECTS,
    }
    for plan in db_session.scalars(sa.select(Plan)):
        missing = metered - set(plan.limits)
        assert not missing, f"{plan.key} does not declare {missing}"
