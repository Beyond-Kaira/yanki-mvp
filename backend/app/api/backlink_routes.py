"""HTTP surface for Backlink Intelligence (Phase 8 / P8.3).

The engine shipped in session 21 and reached no customer: nothing was
registered on the app, so import, delta, authority, toxicity and gap were all
dead code behind a flag. These routes are that missing registration.

Three properties this module is responsible for, none of which the engine can
enforce on its own:

* **Dark when off.** ``BACKLINKS_ENABLED=0`` makes every route 404 — not 403,
  not an empty 200. The flag is a kill switch, and a kill switch that answers
  "forbidden" has still told you the feature exists. It is a router-level
  dependency so a route added later cannot forget it.
* **Permissioned per verb, not per module.** Reading a profile is
  ``backlink:view`` (Viewer and up); refreshing one calls a metered vendor and
  is ``backlink:refresh`` (Analyst and up); taking a copy away is ``export:data``,
  which P7.2 keeps deliberately separate from read because agencies answer
  "can see it" and "can download it" differently for client seats.
* **Money failures are their own status codes.** A quota refusal is 429 and a
  credit refusal is 402, so a UI can say which one happened. Collapsing both
  into 400 is how a customer ends up believing the product is broken when they
  have simply used their plan's refreshes for the month.

Mounted under the SEO project because that is where a customer's domain already
lives; the tenancy-level ``projects`` row it mirrors is what the backlink tables
are actually keyed by.
"""

import csv
import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.backlink_schemas import (
    AnchorClass,
    AnchorDistributionOut,
    BacklinkOut,
    BacklinkPageOut,
    BacklinkSummaryOut,
    CompetitorOut,
    DomainSort,
    InventorySort,
    LinkEventKind,
    LinkEventOut,
    LinkEventPageOut,
    OpportunitiesOut,
    ReferringDomainOut,
    ReferringDomainPageOut,
    RefreshOut,
    RefreshRequest,
    ToxicityBand,
    TrackCompetitorRequest,
)
from app.api.org_dependencies import requires
from app.config import Settings, get_settings
from app.db.session import get_session
from app.services import audit, backlinks, billing
from app.services.permissions import BACKLINK_REFRESH, BACKLINK_VIEW, EXPORT
from app.services.seo_projects import get_org_project
from app.services.tenancy import OrgContext


def require_backlinks_enabled(settings: Annotated[Settings, Depends(get_settings)]) -> None:
    """404 the whole module while the kill switch is off. See the module docstring."""

    if not settings.backlinks_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


router = APIRouter(
    prefix="/api/v1/seo-projects/{project_id}/backlinks",
    tags=["backlinks"],
    dependencies=[Depends(require_backlinks_enabled)],
)


def _subject(session: Session, org: OrgContext, project_id: uuid.UUID) -> backlinks.Subject:
    project = get_org_project(session, org_id=org.require_org_id, project_id=project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="SEO project not found")
    try:
        return backlinks.resolve_subject(project, org_id=org.require_org_id)
    except backlinks.ProjectNotTracked as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this project predates workspace tracking and cannot hold a backlink profile",
        ) from exc


@router.get("/summary", response_model=BacklinkSummaryOut)
def read_summary(
    project_id: uuid.UUID,
    org: OrgContext = Depends(requires(BACKLINK_VIEW)),
    session: Session = Depends(get_session),
) -> BacklinkSummaryOut:
    subject = _subject(session, org, project_id)
    return BacklinkSummaryOut.model_validate(backlinks.summary(session, subject))


@router.get("", response_model=BacklinkPageOut)
def read_backlinks(
    project_id: uuid.UUID,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    anchor_class: AnchorClass | None = None,
    follow: bool | None = None,
    source_domain: str | None = None,
    min_authority: Annotated[float | None, Query(ge=0, le=100)] = None,
    sort: InventorySort = "authority",
    limit: Annotated[int, Query(ge=1, le=backlinks.MAX_PAGE_SIZE)] = backlinks.DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
    org: OrgContext = Depends(requires(BACKLINK_VIEW)),
    session: Session = Depends(get_session),
) -> BacklinkPageOut:
    subject = _subject(session, org, project_id)
    rows, total = backlinks.inventory(
        session,
        subject,
        status=status_filter,
        anchor_class=anchor_class,
        follow=follow,
        source_domain=source_domain,
        min_authority=min_authority,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return BacklinkPageOut(
        total=total,
        limit=limit,
        offset=offset,
        items=[BacklinkOut.model_validate(row) for row in rows],
    )


@router.get("/referring-domains", response_model=ReferringDomainPageOut)
def read_referring_domains(
    project_id: uuid.UUID,
    band: ToxicityBand | None = None,
    sort: DomainSort = "authority",
    limit: Annotated[int, Query(ge=1, le=backlinks.MAX_PAGE_SIZE)] = backlinks.DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
    org: OrgContext = Depends(requires(BACKLINK_VIEW)),
    session: Session = Depends(get_session),
) -> ReferringDomainPageOut:
    subject = _subject(session, org, project_id)
    rows, total = backlinks.referring_domains(
        session, subject, band=band, sort=sort, limit=limit, offset=offset
    )
    return ReferringDomainPageOut(
        total=total,
        limit=limit,
        offset=offset,
        items=[ReferringDomainOut.model_validate(row) for row in rows],
    )


@router.get("/anchors", response_model=AnchorDistributionOut)
def read_anchors(
    project_id: uuid.UUID,
    org: OrgContext = Depends(requires(BACKLINK_VIEW)),
    session: Session = Depends(get_session),
) -> AnchorDistributionOut:
    from app.backlink.gap import anchor_distribution

    subject = _subject(session, org, project_id)
    return AnchorDistributionOut.model_validate(
        anchor_distribution(session, project_id=subject.project_id, subject_domain=subject.domain)
    )


@router.get("/events", response_model=LinkEventPageOut)
def read_events(
    project_id: uuid.UUID,
    kind: LinkEventKind | None = None,
    limit: Annotated[int, Query(ge=1, le=backlinks.MAX_PAGE_SIZE)] = backlinks.DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
    org: OrgContext = Depends(requires(BACKLINK_VIEW)),
    session: Session = Depends(get_session),
) -> LinkEventPageOut:
    subject = _subject(session, org, project_id)
    rows, total = backlinks.events(session, subject, kind=kind, limit=limit, offset=offset)
    return LinkEventPageOut(
        total=total,
        limit=limit,
        offset=offset,
        items=[LinkEventOut.model_validate(row) for row in rows],
    )


@router.get("/opportunities", response_model=OpportunitiesOut)
def read_opportunities(
    project_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=backlinks.MAX_PAGE_SIZE)] = 100,
    org: OrgContext = Depends(requires(BACKLINK_VIEW)),
    session: Session = Depends(get_session),
) -> OpportunitiesOut:
    subject = _subject(session, org, project_id)
    return OpportunitiesOut.model_validate(backlinks.opportunities(session, subject, limit=limit))


@router.post("/refresh", status_code=status.HTTP_201_CREATED, response_model=RefreshOut)
def refresh_backlinks(
    project_id: uuid.UUID,
    payload: RefreshRequest | None = None,
    org: OrgContext = Depends(requires(BACKLINK_REFRESH)),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RefreshOut:
    """Pull one profile from the configured index and diff it against what we believed.

    Synchronous while P8.4's worker wiring is outstanding — see
    ``services.backlinks.refresh``. A vendor that is unreachable does not fail
    this call: the importer records a non-measurable import, mints no losses,
    and the response says so through ``coverage_status``.
    """

    subject = _subject(session, org, project_id)
    try:
        outcome = backlinks.refresh(
            session,
            settings=settings,
            subject=subject,
            trigger=(payload.trigger if payload else "manual"),
        )
    except backlinks.BacklinksUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="no backlink index is configured",
        ) from exc
    except backlinks.RefreshInProgress as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this project already has a backlink refresh running",
        ) from exc
    except billing.QuotaExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"backlink refresh quota exhausted ({exc.used}/{exc.limit} this month)",
        ) from exc
    except billing.InsufficientCredit as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"credit balance {exc.balance} cannot cover an estimated {exc.needed}",
        ) from exc

    audit.emit(
        session,
        action="backlink:refresh",
        context=org,
        actor_type="user",
        actor_id=org.user_id,
        entity_type="backlink_import",
        entity_id=outcome.import_id,
        after={
            "subject_domain": subject.domain,
            "coverage_status": outcome.coverage_status,
            "measurable": outcome.measurable,
            "rows_ingested": outcome.rows_ingested,
            "new_links": outcome.new_links,
            "lost_links": outcome.lost_links,
            "cost_usd": str(outcome.cost_usd),
        },
    )
    session.commit()

    return RefreshOut(
        import_id=outcome.import_id,
        measurable=outcome.measurable,
        coverage_status=outcome.coverage_status,
        rows_ingested=outcome.rows_ingested,
        new_links=outcome.new_links,
        lost_links=outcome.lost_links,
        regained_links=outcome.regained_links,
        changed_links=outcome.changed_links,
        cost_usd=outcome.cost_usd,
    )


@router.get("/competitors", response_model=list[CompetitorOut])
def read_competitors(
    project_id: uuid.UUID,
    org: OrgContext = Depends(requires(BACKLINK_VIEW)),
    session: Session = Depends(get_session),
) -> list[CompetitorOut]:
    subject = _subject(session, org, project_id)
    return [
        CompetitorOut.model_validate(row) for row in backlinks.list_competitors(session, subject)
    ]


@router.post("/competitors", status_code=status.HTTP_201_CREATED, response_model=CompetitorOut)
def track_competitor(
    project_id: uuid.UUID,
    payload: TrackCompetitorRequest,
    org: OrgContext = Depends(requires(BACKLINK_REFRESH)),
    session: Session = Depends(get_session),
) -> CompetitorOut:
    """Track a competitor domain, which is what makes gap analysis have an answer.

    ``backlink:refresh`` rather than ``project:update``: adding a competitor is
    what causes their profile to be pulled, so it is a spending decision.
    """

    subject = _subject(session, org, project_id)
    try:
        row = backlinks.track_competitor(
            session, subject, domain=payload.domain, label=payload.label
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CompetitorOut.model_validate(row)


@router.delete("/competitors/{competitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def untrack_competitor(
    project_id: uuid.UUID,
    competitor_id: uuid.UUID,
    org: OrgContext = Depends(requires(BACKLINK_REFRESH)),
    session: Session = Depends(get_session),
) -> Response:
    subject = _subject(session, org, project_id)
    if not backlinks.untrack_competitor(session, subject, competitor_id=competitor_id):
        raise HTTPException(status_code=404, detail="competitor not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


_CSV_COLUMNS = (
    "source_url",
    "source_domain",
    "target_url",
    "anchor",
    "anchor_class",
    "is_follow",
    "status",
    "first_seen_at",
    "last_seen_at",
    "source_domain_authority",
    "toxicity_score",
    "toxicity_band",
    "vendor",
)


@router.get("/export.csv", response_class=Response)
def export_backlinks_csv(
    project_id: uuid.UUID,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=backlinks.MAX_PAGE_SIZE)] = backlinks.MAX_PAGE_SIZE,
    org: OrgContext = Depends(requires(EXPORT)),
    session: Session = Depends(get_session),
) -> Response:
    """The inventory as CSV, capped at the same page ceiling as the list view.

    Capped deliberately: a full-profile dump belongs in an export artifact
    (plan §4), not in a synchronous request that holds a database connection
    open for a million rows.
    """

    subject = _subject(session, org, project_id)
    rows, _ = backlinks.inventory(session, subject, status=status_filter, limit=limit, offset=0)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_CSV_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                row.source_url,
                row.source_domain,
                row.target_url,
                row.anchor,
                row.anchor_class,
                row.is_follow,
                row.status,
                row.first_seen_at.isoformat() if row.first_seen_at else "",
                row.last_seen_at.isoformat() if row.last_seen_at else "",
                row.source_domain_authority if row.source_domain_authority is not None else "",
                row.toxicity_score if row.toxicity_score is not None else "",
                row.toxicity_band or "",
                row.vendor,
            ]
        )

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="backlinks-{subject.domain}.csv"'},
    )


@router.get("/disavow.txt", response_class=Response)
def export_disavow(
    project_id: uuid.UUID,
    minimum_band: Annotated[str, Query(pattern="^(high|medium)$")] = "high",
    org: OrgContext = Depends(requires(EXPORT)),
    session: Session = Depends(get_session),
) -> Response:
    """A Google-format disavow file, reasons included as comments.

    Advisory, and worded that way in the file's own preamble: submitting a
    disavow is irreversible in effect, and nothing here disavows anything on a
    customer's behalf.
    """

    subject = _subject(session, org, project_id)
    body = backlinks.disavow(session, subject, minimum_band=minimum_band)
    return Response(
        content=body,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="disavow-{subject.domain}.txt"'},
    )
