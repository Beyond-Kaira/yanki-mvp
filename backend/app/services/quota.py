"""The seam where a plan tier stops being decorative (P7.6, ADR-45).

``services.billing`` shipped in session 21 with the whole machinery — the plan
catalog, the usage counters, the credit ledger, ``check_quota`` /
``consume_quota`` / ``reserve`` / ``settle``. What it never had was a caller on
any path a customer touches, so for three sessions every organization was
silently on Free and Free meant nothing.

This module is the missing caller, and it is deliberately thin. It exists for
exactly two reasons that ``billing`` itself should not carry:

1. **The kill switch has one home.** ``QUOTA_ENFORCEMENT_ENABLED`` is read here
   and nowhere else. A route asks this module rather than ``billing`` directly,
   so "is enforcement on" cannot be answered differently in two places.

   **One path does not go through here, and the switch therefore does not cover
   it.** ``backlink.delta`` calls ``billing.reserve`` itself, because it needs
   the *credit* half as well as the count and it predates this module. So
   ``QUOTA_ENFORCEMENT_ENABLED=0`` disables metering on analyses, site audits and
   projects, and leaves backlink refreshes metered. That is currently harmless —
   ``BACKLINKS_ENABLED`` is off in production, so the path is unreachable — and
   it is stated here rather than glossed, because an earlier version of this
   docstring claimed the switch could not half-work and it can (tech-debt #89,
   found by the cross-tenant leakage suite, whose owner-side probe got a 429
   with enforcement switched off).
2. **``billing`` stays free of ``Settings``.** The money layer should be
   callable from a worker, a script and a test without constructing application
   configuration; keeping the flag out here is what preserves that.

Everything else — what a limit is, what a month is, what the ledger says — stays
in ``billing``. This is a gate, not a second implementation of one.

The exceptions travel unchanged: ``QuotaExceeded``, ``InsufficientCredit`` and
``PlanCatalogMissing`` are raised by ``billing`` and turned into 429 / 402 / 503
by the handlers registered in ``api.main``, so no route has to remember to map
them.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import Settings
from app.services import audit, billing
from app.services.tenancy import OrgContext


def consume(
    session: Session,
    settings: Settings,
    *,
    org_id: uuid.UUID,
    metric: str,
    amount: int = 1,
    now: datetime | None = None,
    context: OrgContext | None = None,
) -> None:
    """Check and record one use of a monthly allowance.

    Check-and-increment together, because ``billing.consume_quota`` is written
    that way on purpose: a caller that could do the first without the second is
    the shape of every quota bypass ever written.

    Flushes but does not commit — the counter must land in the same transaction
    as whatever it is paying for, or a request that fails after the check has
    charged a customer for work that never happened.

    ``context`` is optional and only ever used to attribute the *refusal* event;
    a caller that omits it still gets identical enforcement.
    """

    if not settings.quota_enforcement_enabled:
        return
    try:
        billing.consume_quota(session, org_id, metric, amount=amount, now=now)
    except billing.QuotaExceeded as exc:
        _record_refusal(session, org_id=org_id, context=context, exc=exc)
        raise


def check_stock(
    session: Session,
    settings: Settings,
    *,
    org_id: uuid.UUID,
    metric: str,
    current: int,
    amount: int = 1,
    context: OrgContext | None = None,
) -> None:
    """Refuse if the org already holds its allowance of a *thing* (not an event).

    See ``billing.check_stock_quota`` for why projects are counted this way and
    analyses are not.
    """

    if not settings.quota_enforcement_enabled:
        return
    try:
        billing.check_stock_quota(session, org_id, metric, current=current, amount=amount)
    except billing.QuotaExceeded as exc:
        _record_refusal(session, org_id=org_id, context=context, exc=exc)
        raise


def _record_refusal(
    session: Session,
    *,
    org_id: uuid.UUID,
    context: OrgContext | None,
    exc: billing.QuotaExceeded,
) -> None:
    """Write the 429 into the audit trail, in its own committed transaction.

    **Why this is audited at all**, when nothing was mutated: because it is the
    only record that the platform refused to serve a paying customer. Session 25
    made every organization Free by default, so refusals are now the most likely
    thing to happen to a live user, and until this existed the answer to "my
    analysis just fails, why?" existed nowhere — not in the response the user
    forwards to support, not in the logs, nowhere. The spine already records
    refusals: a failed login is an ``auth:login`` with ``outcome="denied"``, and
    this is the same event class for the same reason.

    **Why it commits here.** The request is about to unwind: the route raises,
    the handler in ``api.main`` turns it into a 429, and the session closes
    without committing — so an event merely added to it would be discarded along
    with the refusal it describes. Committing is safe at every call site because
    ``billing.check_quota``/``check_stock_quota`` raise *before* they write, and
    every route runs its quota gate before any other mutation, so the only thing
    pending here is this event. That ordering is asserted by the tests rather
    than assumed; a future metered path that writes first must emit at its own
    call site instead of relying on this.
    """

    # The org is always known — it is an argument. A caller that passed no
    # context gets an event attributed to the organization but not to a person,
    # rather than one with a NULL org, which would be invisible in the Admin
    # Panel's log: the only place anybody would go looking for it.
    attribution = context if context is not None else OrgContext(org_id=org_id)
    audit.emit(
        session,
        action="billing:quota_denied",
        context=attribution,
        actor_type="user" if attribution.user_id is not None else "system",
        actor_id=attribution.user_id,
        entity_type="organization",
        entity_id=org_id,
        outcome="denied",
        detail={"metric": exc.metric, "used": exc.used, "limit": exc.limit},
    )
    session.commit()
