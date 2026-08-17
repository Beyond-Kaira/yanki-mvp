"""Thin orchestration glue between the API layer and the database."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from app.db.models import Analysis, CreditLedgerEntry, GeoRecord, Prompt, Response, SeoCheck, SerpCheck
from app.services import billing
from app.services.tenancy import OrgContext, scoped

# What the ledger calls a charge that came from one GEO analysis. A constant
# because the settle path both writes it and reads it back to stay idempotent,
# and a typo across those two would double-charge silently.
ANALYSIS_SOURCE_TYPE = "analysis"


class AnalysisDeleteConflictError(Exception):
    """The analysis exists but is not in a state that may be deleted manually."""

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(f"analysis in status {status!r} cannot be deleted")


def delete_analysis_children(session: Session, analysis_id: uuid.UUID) -> None:
    """Remove every row owned by one analysis. Shared by re-runs, manual delete,
    and the failed-run auto-purge."""

    session.execute(delete(GeoRecord).where(GeoRecord.analysis_id == analysis_id))
    session.execute(delete(Response).where(Response.analysis_id == analysis_id))
    session.execute(delete(Prompt).where(Prompt.analysis_id == analysis_id))
    session.execute(delete(SerpCheck).where(SerpCheck.analysis_id == analysis_id))
    session.execute(delete(SeoCheck).where(SeoCheck.analysis_id == analysis_id))


def purge_analysis(session: Session, analysis: Analysis, *, commit: bool = True) -> None:
    """Delete an analysis and every child row it owns."""

    delete_analysis_children(session, analysis.id)
    session.delete(analysis)
    if commit:
        session.commit()


def should_auto_purge_failed(analysis: Analysis) -> bool:
    """Whether a failed run should be removed automatically after settle.

    User-owned MVP runs are ephemeral errors for the interim stock limit — they
    never appear in history and must not hold a slot. Legacy and checker runs
    keep the failed envelope (FR-7).
    """

    return (
        analysis.created_by_user_id is not None
        and (analysis.kind or "mvp") in LISTABLE_KINDS
    )


def delete_user_analysis(session: Session, analysis: Analysis, user_id: uuid.UUID) -> None:
    """Remove one finished analysis queued by this user.

    Only ``done`` rows may be deleted manually. ``queued`` and ``running`` are
    in-flight work; ``failed`` rows are removed by the worker auto-purge.
    """

    if analysis.created_by_user_id != user_id:
        raise ValueError("analysis is not owned by this user")
    if analysis.status != "done":
        raise AnalysisDeleteConflictError(analysis.status)
    purge_analysis(session, analysis, commit=False)


def create_analysis(
    session: Session,
    url: str,
    ip_hash: str | None = None,
    *,
    org_id: uuid.UUID | None = None,
    created_by_user_id: uuid.UUID | None = None,
    commit: bool = True,
) -> Analysis:
    """Insert a new queued analysis and return it.

    ``ip_hash`` is the salted hash of the submitter's IP (P5.0 rate limiting);
    it stays optional so existing callers/tests remain valid.

    ``org_id`` is the organization the run belongs to. ``None`` keeps the
    historical "public" scope — every row created before P7.6 has it, and
    ``tenancy.readable_analysis`` is the one place that means world-readable.

    ``created_by_user_id`` records which authenticated user queued the run.
    ``None`` on legacy rows written before the column existed.

    ``commit=False`` hands the transaction boundary back to the caller. The
    metered route needs that: the quota counter and the row it pays for have to
    land together, and a commit in here would leave a charged customer with a
    row that a later failure rolls back — or the reverse.
    """
    analysis = Analysis(
        url=url,
        ip_hash=ip_hash,
        org_id=org_id,
        created_by_user_id=created_by_user_id,
    )
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


# The kinds a history screen is about. `checker` runs are excluded structurally
# rather than by this filter — they are anonymous and carry no `org_id`, so an
# org-scoped query cannot reach one — but naming the set here means a future
# kind has to be added deliberately instead of appearing in someone's history
# because it happened to be persisted in the same table.
LISTABLE_KINDS = ("mvp",)

MAX_PAGE = 100


@dataclass(frozen=True)
class AnalysisPage:
    """One page of history, plus the total the filters matched."""

    total: int
    analyses: list[Analysis]


def _history_statement(
    statement: Select,
    context: OrgContext,
    status: str | None,
    *,
    user_id: uuid.UUID | None = None,
) -> Select:
    # `scoped` rather than a hand-written `where`: it raises on a missing or
    # org-less context instead of quietly returning every tenant's rows, which
    # is the difference between a filter you can forget and one you cannot.
    # This is its first call site in the application (tech-debt #63).
    statement = scoped(statement, Analysis.org_id, context)
    statement = statement.where(Analysis.kind.in_(LISTABLE_KINDS))
    if user_id is not None:
        statement = statement.where(Analysis.created_by_user_id == user_id)
    if status:
        statement = statement.where(Analysis.status == status)
    return statement


def list_org_analyses(
    session: Session,
    context: OrgContext,
    *,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> AnalysisPage:
    """The organization's own analyses, newest first.

    Runs have carried an ``org_id`` since P7.6 and there was no way to list
    them: the only route to a result was the URL you were redirected to, so
    closing the tab lost it (tech-debt #77). This is the read that makes the
    attribution visible to the person paying for it.

    **Summary rows only.** The relationships an analysis owns — prompts,
    responses, SERP and SEO checks, geo records — are deliberately not loaded.
    A single finished run holds dozens of responses, so a page of twenty would
    serialize thousands of rows to render a table of URLs and scores. The
    detail route already exists for the one the reader clicks.

    The sort ends with ``id`` as a tiebreaker. Two runs submitted in the same
    transaction share a timestamp often enough that without it, page 2 can
    repeat a row from page 1 and silently skip another — the same unstable
    pagination the audit log guards against.
    """

    total = int(
        session.scalar(
            select(func.count()).select_from(
                _history_statement(select(Analysis.id), context, status).subquery()
            )
        )
        or 0
    )

    rows = list(
        session.scalars(
            _history_statement(select(Analysis), context, status)
            .order_by(Analysis.created_at.desc(), Analysis.id.desc())
            .limit(max(1, min(limit, MAX_PAGE)))
            .offset(max(0, offset))
        )
    )
    return AnalysisPage(total=total, analyses=rows)


def list_user_analyses(
    session: Session,
    context: OrgContext,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> AnalysisPage:
    """The caller's own analyses within their organization, newest first.

    Org scoping still applies — another tenant's row is absent — and within an
    organization only rows the user queued appear. Legacy rows with no
    ``created_by_user_id`` belong to nobody's history and are excluded here.
    """

    total = int(
        session.scalar(
            select(func.count()).select_from(
                _history_statement(
                    select(Analysis.id), context, status, user_id=user_id
                ).subquery()
            )
        )
        or 0
    )

    rows = list(
        session.scalars(
            _history_statement(select(Analysis), context, status, user_id=user_id)
            .order_by(Analysis.created_at.desc(), Analysis.id.desc())
            .limit(max(1, min(limit, MAX_PAGE)))
            .offset(max(0, offset))
        )
    )
    return AnalysisPage(total=total, analyses=rows)


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
