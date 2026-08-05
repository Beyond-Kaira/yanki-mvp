"""Plans, quotas and the credit ledger — the layer that makes spend real (P7.6).

Two questions, deliberately answered by two different mechanisms:

* **"May this org do one more of these?"** — :func:`check_quota`, backed by
  :class:`UsageCounter`. A small counter per (org, metric, window), updated in
  place. Fast, and the answer a request needs before it starts work.
* **"What has this org actually spent?"** — :func:`record_charge`, backed by an
  **append-only, signed** ledger. Nothing updates a row: correcting a mistake
  means writing its reversal, so both the error and the correction stay visible.
  A mutable balance column would be faster and would also be the number nobody
  could ever reconcile.

Conflating the two is the tempting design and the wrong one — it would make
either the money mutable or the quota check a sum over all history.

**The reserve-then-settle shape matters.** A paid call is reserved *before* it
is made, at an estimate, and settled at the real cost afterwards. Charging only
on success means a call that succeeded upstream and then crashed locally is
spend that never appears — which is exactly how the measured GEO path lost a
week of cost data (ADR-34). Reserving first means the worst failure is an
over-estimate, which is recoverable, rather than an invisible charge, which is
not.

Stripe is deliberately absent. This card needs "what may this org do" to have
an answer, not a billing lifecycle; the Stripe columns exist so adding one is
an UPDATE rather than a migration on a populated table.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import CreditLedgerEntry, Plan, Subscription, UsageCounter

# Metric keys. Strings, like permissions, so a new metered thing needs no
# migration — M2's backlink rows already fit.
METRIC_ANALYSES = "analyses"
METRIC_SITE_AUDITS = "site_audits"
METRIC_BACKLINK_REFRESHES = "backlink_refreshes"
METRIC_PROJECTS = "projects"

# The baseline's tiers, seeded as data. `None` means unlimited, which is
# distinct from 0 (meaning "not available on this plan") — a distinction that
# matters because a Free plan with 0 backlink refreshes and an Enterprise plan
# with unlimited ones must not be represented by the same value.
DEFAULT_PLANS: tuple[dict, ...] = (
    {
        "key": "free",
        "name": "Free",
        "monthly_price_usd": Decimal("0"),
        "limits": {
            METRIC_ANALYSES: 5,
            METRIC_SITE_AUDITS: 1,
            METRIC_BACKLINK_REFRESHES: 0,
            METRIC_PROJECTS: 1,
            "monthly_credit_usd": "0",
        },
    },
    {
        "key": "starter",
        "name": "Starter",
        "monthly_price_usd": Decimal("49"),
        "limits": {
            METRIC_ANALYSES: 100,
            METRIC_SITE_AUDITS: 20,
            METRIC_BACKLINK_REFRESHES: 4,
            METRIC_PROJECTS: 3,
            "monthly_credit_usd": "10",
        },
    },
    {
        "key": "pro",
        "name": "Pro",
        "monthly_price_usd": Decimal("149"),
        "limits": {
            METRIC_ANALYSES: 500,
            METRIC_SITE_AUDITS: 100,
            METRIC_BACKLINK_REFRESHES: 30,
            METRIC_PROJECTS: 10,
            "monthly_credit_usd": "50",
        },
    },
    {
        "key": "business",
        "name": "Business",
        "monthly_price_usd": Decimal("399"),
        "limits": {
            METRIC_ANALYSES: 2000,
            METRIC_SITE_AUDITS: 500,
            METRIC_BACKLINK_REFRESHES: 120,
            METRIC_PROJECTS: 50,
            "monthly_credit_usd": "200",
        },
    },
    {
        "key": "enterprise",
        "name": "Enterprise",
        "monthly_price_usd": Decimal("0"),
        "limits": {
            METRIC_ANALYSES: None,
            METRIC_SITE_AUDITS: None,
            METRIC_BACKLINK_REFRESHES: None,
            METRIC_PROJECTS: None,
            "monthly_credit_usd": None,
        },
    },
)


class QuotaExceeded(RuntimeError):
    """The org has used its allowance of something."""

    def __init__(self, metric: str, used: int, limit: int) -> None:
        super().__init__(f"{metric} quota exhausted ({used}/{limit})")
        self.metric = metric
        self.used = used
        self.limit = limit


class InsufficientCredit(RuntimeError):
    """The org cannot afford what it is about to be charged."""

    def __init__(self, balance: Decimal, needed: Decimal) -> None:
        super().__init__(f"balance {balance} cannot cover {needed}")
        self.balance = balance
        self.needed = needed


@dataclass(frozen=True)
class Reservation:
    """A held estimate, to be settled at the real cost."""

    org_id: uuid.UUID
    metric: str
    estimate_usd: Decimal
    entry_id: uuid.UUID | None


def seed_plans(session: Session) -> int:
    """Insert the default catalog. Idempotent — safe on every boot."""

    existing = {row[0] for row in session.execute(select(Plan.key))}
    added = 0
    for spec in DEFAULT_PLANS:
        if spec["key"] in existing:
            continue
        session.add(
            Plan(
                key=spec["key"],
                name=spec["name"],
                limits=spec["limits"],
                monthly_price_usd=spec["monthly_price_usd"],
            )
        )
        added += 1
    session.flush()
    return added


def plan_for_org(session: Session, org_id: uuid.UUID) -> Plan | None:
    """The org's current plan, or None if it has no live subscription."""

    return session.scalar(
        select(Plan)
        .join(Subscription, Subscription.plan_id == Plan.id)
        .where(
            Subscription.org_id == org_id,
            Subscription.status.in_(("trialing", "active", "past_due")),
        )
        .limit(1)
    )


def limit_for(session: Session, org_id: uuid.UUID, metric: str) -> int | None:
    """The org's allowance of ``metric``. ``None`` means unlimited.

    An org with no subscription falls back to Free rather than to unlimited.
    That direction is not arbitrary: an unknown plan defaulting to unlimited
    would make every misconfiguration a free-spend bug.
    """

    plan = plan_for_org(session, org_id)
    if plan is None:
        free = session.scalar(select(Plan).where(Plan.key == "free"))
        plan = free
    if plan is None:
        return 0
    if metric not in plan.limits:
        # An unmetered thing is unlimited; a metered thing missing from a plan
        # would be a seeding bug, and 0 there would break the product silently.
        return None
    return plan.limits[metric]


def _window_start(now: datetime | None = None) -> datetime:
    """The calendar month, which is what a monthly allowance means to a customer."""

    moment = now or datetime.now(UTC)
    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def usage(session: Session, org_id: uuid.UUID, metric: str, *, now: datetime | None = None) -> int:
    counter = session.scalar(
        select(UsageCounter).where(
            UsageCounter.org_id == org_id,
            UsageCounter.metric == metric,
            UsageCounter.window_start == _window_start(now),
        )
    )
    return counter.used if counter else 0


def check_quota(
    session: Session,
    org_id: uuid.UUID,
    metric: str,
    *,
    amount: int = 1,
    now: datetime | None = None,
) -> None:
    """Raise :class:`QuotaExceeded` if this would exceed the allowance."""

    limit = limit_for(session, org_id, metric)
    if limit is None:
        return
    used = usage(session, org_id, metric, now=now)
    if used + amount > limit:
        raise QuotaExceeded(metric, used, limit)


def consume_quota(
    session: Session,
    org_id: uuid.UUID,
    metric: str,
    *,
    amount: int = 1,
    now: datetime | None = None,
) -> int:
    """Check, then record the use. Returns the new total.

    Check and increment are one call so no path can do the first without the
    second — which is the shape of every quota bypass ever written.
    """

    check_quota(session, org_id, metric, amount=amount, now=now)
    window = _window_start(now)
    counter = session.scalar(
        select(UsageCounter).where(
            UsageCounter.org_id == org_id,
            UsageCounter.metric == metric,
            UsageCounter.window_start == window,
        )
    )
    if counter is None:
        counter = UsageCounter(org_id=org_id, metric=metric, window_start=window, used=0)
        session.add(counter)
    counter.used += amount
    session.flush()
    return counter.used


def balance(session: Session, org_id: uuid.UUID) -> Decimal:
    """The org's credit balance: the sum of every signed ledger entry."""

    total = session.scalar(
        select(func.coalesce(func.sum(CreditLedgerEntry.delta_usd), 0)).where(
            CreditLedgerEntry.org_id == org_id
        )
    )
    return Decimal(str(total or 0))


def grant_credit(
    session: Session,
    org_id: uuid.UUID,
    amount: Decimal,
    *,
    reason: str = "grant",
    actor_id: uuid.UUID | None = None,
    detail: dict | None = None,
) -> CreditLedgerEntry:
    """Add credit. Positive delta, and the only way a balance goes up."""

    return _append(
        session,
        org_id,
        Decimal(amount),
        reason=reason,
        actor_id=actor_id,
        detail=detail,
        source_type="grant",
    )


def record_charge(
    session: Session,
    org_id: uuid.UUID,
    amount: Decimal,
    *,
    reason: str,
    source_type: str | None = None,
    source_id: uuid.UUID | None = None,
    detail: dict | None = None,
    allow_negative: bool = True,
) -> CreditLedgerEntry:
    """Record spend. Negative delta.

    ``allow_negative`` defaults True on purpose: this is called *after* money
    has already been spent upstream, and refusing to record a real charge
    because it takes the balance below zero would make the ledger a comforting
    fiction. Refusal belongs before the call (:func:`reserve`), not after it.
    """

    charge = -abs(Decimal(amount))
    if not allow_negative and balance(session, org_id) + charge < 0:
        raise InsufficientCredit(balance(session, org_id), abs(charge))
    return _append(
        session,
        org_id,
        charge,
        reason=reason,
        source_type=source_type,
        source_id=source_id,
        detail=detail,
    )


def _append(
    session: Session,
    org_id: uuid.UUID,
    delta: Decimal,
    *,
    reason: str,
    source_type: str | None = None,
    source_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    detail: dict | None = None,
) -> CreditLedgerEntry:
    entry = CreditLedgerEntry(
        org_id=org_id,
        delta_usd=delta,
        balance_after_usd=balance(session, org_id) + delta,
        reason=reason,
        source_type=source_type,
        source_id=source_id,
        actor_id=actor_id,
        detail=detail,
    )
    session.add(entry)
    session.flush()
    return entry


def reserve(
    session: Session,
    org_id: uuid.UUID,
    *,
    metric: str,
    estimate_usd: Decimal,
    now: datetime | None = None,
) -> Reservation:
    """Hold quota and check affordability BEFORE a paid call is made.

    Refusal happens here, where nothing has been spent yet. Once the vendor has
    answered, the charge is a fact and :func:`settle` records it whatever the
    balance says.
    """

    consume_quota(session, org_id, metric, now=now)
    available = balance(session, org_id)
    if estimate_usd > 0 and available < estimate_usd:
        raise InsufficientCredit(available, estimate_usd)
    return Reservation(
        org_id=org_id, metric=metric, estimate_usd=Decimal(estimate_usd), entry_id=None
    )


def settle(
    session: Session,
    reservation: Reservation,
    actual_usd: Decimal,
    *,
    source_type: str | None = None,
    source_id: uuid.UUID | None = None,
) -> CreditLedgerEntry | None:
    """Record what the reserved call actually cost. Zero is still recorded.

    A $0 settle writes a row rather than skipping: "this ran and cost nothing"
    and "this never ran" are different facts, and the ledger is where the
    difference is visible. It is also what makes the DRY_RUN suite's $0
    assertions mean something.
    """

    return record_charge(
        session,
        reservation.org_id,
        Decimal(actual_usd),
        reason=reservation.metric,
        source_type=source_type,
        source_id=source_id,
        detail={"estimate_usd": str(reservation.estimate_usd)},
    )
