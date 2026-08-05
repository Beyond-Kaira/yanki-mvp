"""The read and refresh layer between the backlink engine and its HTTP surface.

Phase 8 shipped an engine with no way in: ``app/backlink/`` could import, diff,
score, and export, and nothing called it. This module is the missing half — it
turns "a customer's SEO project" into the arguments the engine wants, and turns
what the engine returns into shapes a route can serialize.

Three decisions worth stating, because each has a wrong version that looks fine:

* **One subject key, computed one way.** Every table in the module is keyed by a
  normalized ``subject_domain``, and a read that normalizes differently from the
  write silently returns an empty profile — the failure mode where the product
  says "no backlinks" about a domain it has thousands of rows for. So reads and
  writes both go through :func:`subject_for`, and nothing else derives the key.
  ``SeoProject.domain_key`` is deliberately *not* used: it is computed by the
  Site Audit normalizer, which is a different function that happens to agree
  today.
* **The cycle is the count of prior imports.** The mock is a pure function of
  ``(domain, cycle)``, so the cycle is what makes a second refresh differ from
  the first. Counting completed imports keeps that property without a clock,
  and means the DRY_RUN demo path evolves exactly the way the tests do.
* **Authority and toxicity are recomputed here, not in the importer.**
  ``run_import`` stops at the rollups on purpose — it owns the delta, and the
  scores are functions *of* the rollups it just rebuilt. Recomputing them
  immediately after, in the same transaction, is what keeps a stored score from
  ever describing a profile that no longer exists.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.backlink.authority import compute_authority, velocity
from app.backlink.delta import ImportOutcome, run_import
from app.backlink.gap import anchor_distribution, outreach_list
from app.backlink.normalize import domain_key
from app.backlink.registry import get_backlink_source
from app.backlink.toxicity import assess_project, disavow_file
from app.db.models import (
    Backlink,
    BacklinkCompetitor,
    BacklinkImport,
    LinkEvent,
    ReferringDomainRollup,
    SeoProject,
)

# Every list endpoint is capped. The inventory is the one place in the product
# where a single project can hold six figures of rows, and an uncapped list is a
# denial of service against ourselves.
MAX_PAGE_SIZE = 500
DEFAULT_PAGE_SIZE = 50


class BacklinksUnavailable(RuntimeError):
    """No index is configured, so nothing can be refreshed.

    Distinct from "the module is off" (which the route answers as 404, keeping
    the surface dark) and from "the vendor failed" (which the importer absorbs
    into a non-measurable import). This is the honest answer while operator
    item A4 is unanswered: switched on, but no vendor behind it.
    """


class ProjectNotTracked(RuntimeError):
    """The SEO project predates tenancy and has no ``projects`` row to hang from.

    Backlink rows are keyed by the tenancy-level project, so a project created
    before P7.1 mirrored one has nowhere to store a profile. Refusing loudly
    beats writing rows under a null owner.
    """


class RefreshInProgress(RuntimeError):
    """This subject already has a queued or running import."""


@dataclass(frozen=True)
class Subject:
    """What the engine needs to talk about one project's own domain."""

    org_id: uuid.UUID
    project_id: uuid.UUID
    domain: str
    brand: str


def subject_for(project: SeoProject) -> str:
    """The one normalization. See the module docstring."""

    return domain_key(project.domain) or project.domain


def resolve_subject(project: SeoProject, *, org_id: uuid.UUID) -> Subject:
    if project.project_id is None:
        raise ProjectNotTracked
    return Subject(
        org_id=org_id,
        project_id=project.project_id,
        domain=subject_for(project),
        brand=project.name or "",
    )


def next_cycle(session: Session, subject: Subject) -> int:
    """How many imports have already concluded for this subject."""

    return int(
        session.scalar(
            select(func.count())
            .select_from(BacklinkImport)
            .where(
                BacklinkImport.project_id == subject.project_id,
                BacklinkImport.subject_domain == subject.domain,
                BacklinkImport.status.in_(("done", "partial", "failed")),
            )
        )
        or 0
    )


def active_import(session: Session, subject: Subject) -> BacklinkImport | None:
    return session.scalar(
        select(BacklinkImport).where(
            BacklinkImport.project_id == subject.project_id,
            BacklinkImport.subject_domain == subject.domain,
            BacklinkImport.status.in_(("queued", "running")),
        )
    )


def latest_import(session: Session, subject: Subject) -> BacklinkImport | None:
    return session.scalar(
        select(BacklinkImport)
        .where(
            BacklinkImport.project_id == subject.project_id,
            BacklinkImport.subject_domain == subject.domain,
            BacklinkImport.status.in_(("done", "partial")),
        )
        .order_by(BacklinkImport.created_at.desc())
        .limit(1)
    )


def refresh(
    session: Session,
    *,
    settings: Any,
    subject: Subject,
    trigger: str = "manual",
    now: datetime | None = None,
) -> ImportOutcome:
    """Run one metered refresh, then rescore the profile it produced.

    Synchronous, and that is a considered interim: P8.4's residual is the worker
    wiring, and until it lands a request-scoped import is the only way the
    module has a customer-visible pulse. The vendor call is bounded by the quota
    reservation inside ``run_import``, so "synchronous" cannot mean "unbounded".
    """

    moment = now or datetime.now(UTC)
    source = get_backlink_source(settings, cycle=next_cycle(session, subject))
    if source is None:
        raise BacklinksUnavailable

    if active_import(session, subject) is not None:
        raise RefreshInProgress

    try:
        outcome = run_import(
            session,
            source=source,
            org_id=subject.org_id,
            project_id=subject.project_id,
            subject_domain=subject.domain,
            brand=subject.brand,
            trigger=trigger,
            now=moment,
        )
    except IntegrityError as exc:
        # The partial unique index is the real guard against a concurrent
        # refresh; the check above only makes the common case a clean 409.
        session.rollback()
        raise RefreshInProgress from exc

    # Scores describe the rollups the import just rebuilt, so they are computed
    # from them rather than carried over. A failed import rebuilt nothing, and
    # rescoring it would overwrite a good score with an empty one.
    if outcome.coverage_status != "failed":
        assess_project(session, project_id=subject.project_id, subject_domain=subject.domain)
        score = compute_authority(
            session, project_id=subject.project_id, subject_domain=subject.domain
        )
        record = session.get(BacklinkImport, outcome.import_id)
        if record is not None:
            record.yanki_authority = score.value
            record.authority_version = score.version
            record.authority_components = score.components

    session.commit()
    return outcome


def summary(session: Session, subject: Subject) -> dict[str, Any]:
    """The profile header: what we believe, how sure we are, and who said so."""

    record = latest_import(session, subject)
    live = session.scalar(
        select(func.count())
        .select_from(Backlink)
        .where(
            Backlink.project_id == subject.project_id,
            Backlink.subject_domain == subject.domain,
            Backlink.status == "active",
        )
    )
    referring = session.scalar(
        select(func.count())
        .select_from(ReferringDomainRollup)
        .where(
            ReferringDomainRollup.project_id == subject.project_id,
            ReferringDomainRollup.subject_domain == subject.domain,
            ReferringDomainRollup.subject_kind == "own",
            ReferringDomainRollup.links_count > 0,
        )
    )
    follow = session.scalar(
        select(func.count())
        .select_from(Backlink)
        .where(
            Backlink.project_id == subject.project_id,
            Backlink.subject_domain == subject.domain,
            Backlink.status == "active",
            Backlink.is_follow.is_(True),
        )
    )
    lost = session.scalar(
        select(func.count())
        .select_from(Backlink)
        .where(
            Backlink.project_id == subject.project_id,
            Backlink.subject_domain == subject.domain,
            Backlink.status.in_(("lost", "lost_unverified")),
        )
    )

    return {
        "subject_domain": subject.domain,
        "backlinks": int(live or 0),
        "follow_links": int(follow or 0),
        "referring_domains": int(referring or 0),
        "lost_links": int(lost or 0),
        "authority": record.yanki_authority if record else None,
        "authority_version": record.authority_version if record else None,
        "authority_components": record.authority_components if record else None,
        "last_import": _import_dict(record) if record else None,
        "velocity": velocity(session, project_id=subject.project_id, subject_domain=subject.domain),
        "anchors": anchor_distribution(
            session, project_id=subject.project_id, subject_domain=subject.domain
        ),
        "toxicity": toxicity_bands(session, subject),
    }


def _import_dict(record: BacklinkImport) -> dict[str, Any]:
    return {
        "id": record.id,
        "status": record.status,
        "vendor": record.vendor,
        "trigger": record.trigger,
        "coverage_status": record.coverage_status,
        # Surfaced, never hidden: an unmeasurable import is the reason a "lost"
        # count did not move, and a customer comparing us to another index
        # deserves to see that rather than infer it.
        "measurable": record.measurable,
        "rows_ingested": record.rows_ingested,
        "reported_total_backlinks": record.reported_total_backlinks,
        "reported_total_referring_domains": record.reported_total_referring_domains,
        "new_in_period": record.new_in_period,
        "lost_in_period": record.lost_in_period,
        "cost_usd": str(Decimal(record.cost_usd or 0)),
        "snapshot_at": record.snapshot_at,
        "completed_at": record.completed_at,
        "error": record.error,
        "provenance": record.provenance,
    }


def toxicity_bands(session: Session, subject: Subject) -> dict[str, int]:
    rows = session.execute(
        select(ReferringDomainRollup.toxicity_band, func.count())
        .where(
            ReferringDomainRollup.project_id == subject.project_id,
            ReferringDomainRollup.subject_domain == subject.domain,
            ReferringDomainRollup.subject_kind == "own",
            ReferringDomainRollup.links_count > 0,
        )
        .group_by(ReferringDomainRollup.toxicity_band)
    )
    counts = {"low": 0, "medium": 0, "high": 0}
    for band, count in rows:
        counts[band or "low"] = counts.get(band or "low", 0) + int(count)
    return counts


def inventory(
    session: Session,
    subject: Subject,
    *,
    status: str | None = None,
    anchor_class: str | None = None,
    follow: bool | None = None,
    source_domain: str | None = None,
    min_authority: float | None = None,
    sort: str = "authority",
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> tuple[list[Backlink], int]:
    """One filtered page of links, plus the total the filter matched.

    The total is a second query rather than ``len(rows)`` because the page is
    capped: a UI that pages through 40,000 links needs to know that, and
    reporting the page size as the total is how a product quietly claims a
    customer has 50 backlinks.
    """

    conditions = [
        Backlink.project_id == subject.project_id,
        Backlink.subject_domain == subject.domain,
    ]
    # 'active' by default: the inventory answers "what links to me", and the
    # lost ones are a different question with its own view.
    conditions.append(Backlink.status == (status or "active"))
    if anchor_class:
        conditions.append(Backlink.anchor_class == anchor_class)
    if follow is not None:
        conditions.append(Backlink.is_follow.is_(follow))
    if source_domain:
        conditions.append(Backlink.source_domain == domain_key(source_domain))
    if min_authority is not None:
        conditions.append(Backlink.source_domain_authority >= min_authority)

    total = int(session.scalar(select(func.count()).select_from(Backlink).where(*conditions)) or 0)

    # Annotated because a dict of ORM ordering expressions widens to ``object``
    # and mypy then refuses the order_by; the values are all UnaryExpression.
    order: Any = {
        "authority": Backlink.source_domain_authority.desc(),
        "first_seen": Backlink.first_seen_at.desc(),
        "last_seen": Backlink.last_seen_at.desc(),
        "toxicity": Backlink.toxicity_score.desc(),
        "domain": Backlink.source_domain.asc(),
    }.get(sort, Backlink.source_domain_authority.desc())

    rows = list(
        session.scalars(
            select(Backlink)
            .where(*conditions)
            # A stable secondary key: ordering by a nullable metric alone gives
            # a different page 2 on every request, which reads as data churn.
            .order_by(order, Backlink.source_url_key.asc())
            .limit(min(limit, MAX_PAGE_SIZE))
            .offset(offset)
        )
    )
    return rows, total


def referring_domains(
    session: Session,
    subject: Subject,
    *,
    band: str | None = None,
    sort: str = "authority",
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> tuple[list[ReferringDomainRollup], int]:
    conditions = [
        ReferringDomainRollup.project_id == subject.project_id,
        ReferringDomainRollup.subject_domain == subject.domain,
        ReferringDomainRollup.subject_kind == "own",
        ReferringDomainRollup.links_count > 0,
    ]
    if band:
        conditions.append(ReferringDomainRollup.toxicity_band == band)

    total = int(
        session.scalar(select(func.count()).select_from(ReferringDomainRollup).where(*conditions))
        or 0
    )
    order: Any = {
        "authority": ReferringDomainRollup.domain_authority.desc(),
        "links": ReferringDomainRollup.links_count.desc(),
        "toxicity": ReferringDomainRollup.toxicity_score.desc(),
        "domain": ReferringDomainRollup.referring_domain.asc(),
    }.get(sort, ReferringDomainRollup.domain_authority.desc())

    rows = list(
        session.scalars(
            select(ReferringDomainRollup)
            .where(*conditions)
            .order_by(order, ReferringDomainRollup.referring_domain.asc())
            .limit(min(limit, MAX_PAGE_SIZE))
            .offset(offset)
        )
    )
    return rows, total


def events(
    session: Session,
    subject: Subject,
    *,
    kind: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> tuple[list[LinkEvent], int]:
    conditions = [
        LinkEvent.project_id == subject.project_id,
        LinkEvent.subject_domain == subject.domain,
    ]
    if kind:
        conditions.append(LinkEvent.kind == kind)

    total = int(session.scalar(select(func.count()).select_from(LinkEvent).where(*conditions)) or 0)
    rows = list(
        session.scalars(
            select(LinkEvent)
            .where(*conditions)
            .order_by(LinkEvent.occurred_at.desc(), LinkEvent.id.asc())
            .limit(min(limit, MAX_PAGE_SIZE))
            .offset(offset)
        )
    )
    return rows, total


def opportunities(session: Session, subject: Subject, *, limit: int = 100) -> dict[str, Any]:
    return outreach_list(
        session,
        project_id=subject.project_id,
        own_domain=subject.domain,
        limit=min(limit, MAX_PAGE_SIZE),
    )


def disavow(session: Session, subject: Subject, *, minimum_band: str = "high") -> str:
    return disavow_file(
        session,
        project_id=subject.project_id,
        subject_domain=subject.domain,
        minimum_band=minimum_band,
    )


def list_competitors(session: Session, subject: Subject) -> list[BacklinkCompetitor]:
    return list(
        session.scalars(
            select(BacklinkCompetitor)
            .where(BacklinkCompetitor.project_id == subject.project_id)
            .order_by(BacklinkCompetitor.competitor_domain.asc())
        )
    )


def track_competitor(
    session: Session, subject: Subject, *, domain: str, label: str | None = None
) -> BacklinkCompetitor:
    """Track one competitor domain. Idempotent: re-tracking reactivates.

    Returning the existing row rather than raising on a duplicate is deliberate
    — the table's unique constraint is about storage, and "track acme.com" is a
    statement of intent that is equally true the second time it is made.
    """

    key = domain_key(domain)
    if not key:
        raise ValueError("competitor domain must not be blank")
    if key == subject.domain:
        raise ValueError("a project cannot be its own competitor")

    existing = session.scalar(
        select(BacklinkCompetitor).where(
            BacklinkCompetitor.project_id == subject.project_id,
            BacklinkCompetitor.competitor_domain == key,
        )
    )
    if existing is not None:
        existing.active = True
        if label:
            existing.label = label
        session.commit()
        return existing

    row = BacklinkCompetitor(
        org_id=subject.org_id,
        project_id=subject.project_id,
        competitor_domain=key,
        label=label,
    )
    session.add(row)
    session.commit()
    return row


def untrack_competitor(session: Session, subject: Subject, *, competitor_id: uuid.UUID) -> bool:
    row = session.scalar(
        select(BacklinkCompetitor).where(
            BacklinkCompetitor.id == competitor_id,
            BacklinkCompetitor.project_id == subject.project_id,
        )
    )
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True
