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
   so "is enforcement on" cannot be answered differently in two places — and
   turning it off cannot half-work, leaving one path metered and another not.
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
from app.services import billing


def consume(
    session: Session,
    settings: Settings,
    *,
    org_id: uuid.UUID,
    metric: str,
    amount: int = 1,
    now: datetime | None = None,
) -> None:
    """Check and record one use of a monthly allowance.

    Check-and-increment together, because ``billing.consume_quota`` is written
    that way on purpose: a caller that could do the first without the second is
    the shape of every quota bypass ever written.

    Flushes but does not commit — the counter must land in the same transaction
    as whatever it is paying for, or a request that fails after the check has
    charged a customer for work that never happened.
    """

    if not settings.quota_enforcement_enabled:
        return
    billing.consume_quota(session, org_id, metric, amount=amount, now=now)


def check_stock(
    session: Session,
    settings: Settings,
    *,
    org_id: uuid.UUID,
    metric: str,
    current: int,
    amount: int = 1,
) -> None:
    """Refuse if the org already holds its allowance of a *thing* (not an event).

    See ``billing.check_stock_quota`` for why projects are counted this way and
    analyses are not.
    """

    if not settings.quota_enforcement_enabled:
        return
    billing.check_stock_quota(session, org_id, metric, current=current, amount=amount)
