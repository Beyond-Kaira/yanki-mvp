"""Thin orchestration glue between the API layer and the database."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Analysis, CreditLedgerEntry, Response
from app.services import billing

# What the ledger calls a charge that came from one GEO analysis. A constant
# because the settle path both writes it and reads it back to stay idempotent,
# and a typo across those two would double-charge silently.
ANALYSIS_SOURCE_TYPE = "analysis"


def create_analysis(
    session: Session,
    url: str,
    ip_hash: str | None = None,
    *,
    org_id: uuid.UUID | None = None,
    commit: bool = True,
) -> Analysis:
    """Insert a new queued analysis and return it.

    ``ip_hash`` is the salted hash of the submitter's IP (P5.0 rate limiting);
    it stays optional so existing callers/tests remain valid.

    ``org_id`` is the organization the run belongs to. ``None`` keeps the
    historical "public" scope — every row created before P7.6 has it, and
    ``tenancy.readable_analysis`` is the one place that means world-readable.

    ``commit=False`` hands the transaction boundary back to the caller. The
    metered route needs that: the quota counter and the row it pays for have to
    land together, and a commit in here would leave a charged customer with a
    row that a later failure rolls back — or the reverse.
    """
    analysis = Analysis(url=url, ip_hash=ip_hash, org_id=org_id)
    session.add(analysis)
    if commit:
        session.commit()
    else:
        session.flush()
    return analysis


def get_analysis(session: Session, analysis_id: uuid.UUID) -> Analysis | None:
    """Fetch an analysis by id, or None if it does not exist.

    Unscoped on purpose — this is the raw read. Callers that serve a request use
    ``tenancy.readable_analysis``, which is where the "who may see this" rule
    lives.
    """
    return session.get(Analysis, analysis_id)


def spend_on(session: Session, analysis_id: uuid.UUID) -> Decimal:
    """What one analysis actually cost, summed from its stored responses."""

    total = session.scalar(
        select(func.coalesce(func.sum(Response.cost_usd), 0)).where(
            Response.analysis_id == analysis_id
        )
    )
    return Decimal(str(total or 0))


def already_charged(session: Session, analysis_id: uuid.UUID) -> Decimal:
    """How much of this analysis has already reached the credit ledger."""

    total = session.scalar(
        select(func.coalesce(func.sum(CreditLedgerEntry.delta_usd), 0)).where(
            CreditLedgerEntry.source_type == ANALYSIS_SOURCE_TYPE,
            CreditLedgerEntry.source_id == analysis_id,
        )
    )
    # Ledger deltas are signed and a charge is negative; the caller thinks in
    # positive money spent.
    return -Decimal(str(total or 0))


def settle_cost(session: Session, analysis: Analysis) -> CreditLedgerEntry | None:
    """Record what a finished analysis cost, against the org that ran it.

    Called by the worker when a run reaches a terminal state — **including
    ``failed``**. A run that died in step five still paid for steps one to four,
    and a ledger that only records successes is the same lie ADR-34 was written
    about: cost computed, then thrown away.

    Three properties worth stating, because each one is a bug if it is missing:

    * **Idempotent.** ``claim_next`` retries a job up to ``MAX_ATTEMPTS``, so
      this can run three times for one analysis. It charges the *difference*
      between what the run has now spent and what the ledger already holds for
      it, which is both re-entrant and correct when a retry genuinely spends
      more.
    * **Public runs are skipped.** An analysis with no ``org_id`` has nobody to
      bill; the credit ledger requires an organization and inventing one would
      be worse than the gap.
    * **It never fails the job.** The run's outcome is already recorded in
      ``analyses``; losing the ledger row is bad, losing the analysis is worse.
      The caller wraps this, and the loss is logged rather than swallowed
      silently.
    """

    if analysis.org_id is None:
        return None

    outstanding = spend_on(session, analysis.id) - already_charged(session, analysis.id)
    if outstanding <= 0:
        # Nothing new to record. Note this is not the same as "cost nothing":
        # a genuinely $0 run writes its zero row the first time through, because
        # "this ran and cost nothing" and "this never ran" are different facts.
        if already_charged(session, analysis.id) != 0 or _has_ledger_row(session, analysis.id):
            return None
        outstanding = Decimal("0")

    return billing.record_charge(
        session,
        analysis.org_id,
        outstanding,
        reason=billing.METRIC_ANALYSES,
        source_type=ANALYSIS_SOURCE_TYPE,
        source_id=analysis.id,
        detail={"status": analysis.status, "kind": analysis.kind or "mvp"},
    )


def _has_ledger_row(session: Session, analysis_id: uuid.UUID) -> bool:
    """Whether this analysis has any ledger row at all, $0 included."""

    return (
        session.scalar(
            select(func.count())
            .select_from(CreditLedgerEntry)
            .where(
                CreditLedgerEntry.source_type == ANALYSIS_SOURCE_TYPE,
                CreditLedgerEntry.source_id == analysis_id,
            )
        )
        or 0
    ) > 0
