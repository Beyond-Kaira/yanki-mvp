"""Authenticated API for SEO projects and their independent Site Audit jobs.

These routes predate P7.2's permission seam and, until 2026-08-05, took only
``get_org_context`` — which answers *on whose behalf* and deliberately never
answers *may they*. The result was that every member of an organization could
create a project and start a crawl, **including a Guest**: the free client seat
whose whole purpose is to be structurally unable to reach internal lanes. Not a
cross-tenant leak (the scoping was correct throughout) but a real hole in the
role model this milestone claims to enforce.

Each route now names the permission it needs, like the Admin Panel's do. The
mapping is the obvious one and follows the matrix rather than inventing grants:
reading is ``project:read``, creating a project is ``project:create``, and
starting a crawl is ``site_audit:run`` — which Analyst and above hold and Guest
and Viewer do not, because a crawl spends real resources against a third-party
site.

On top of the permission check, the *crawl* is gated by a feature flag
(``config.site_audit_enabled``). No deployed service drains the site-audit
queue today, so an enqueued audit would sit ``queued`` forever; until an audit
worker ships, no crawl is started. But that gate must fall on the crawl alone,
not on the SEO project, because the project is the *shared* entity Backlinks
also hangs off (``backlink_routes`` mounts under it). So the two enqueue points
are gated differently, on purpose:

* ``POST /{project_id}/audits`` — starting a fresh crawl on an existing project
  — carries ``require_site_audit_enabled`` and is refused **404** while the flag
  is off. There is nothing else this route does.
* ``POST ""`` (create project) stays **open**; it forwards the flag to
  ``create_project_with_audit`` as ``queue_audit=``, which creates the project
  (and its tenancy mirror) but skips the ``SiteAudit`` row while the flag is
  off. Gating this route instead would let ``SITE_AUDIT_ENABLED=0`` silently
  block Backlinks — a customer could not create a project to attach a profile to.

Reads stay open throughout so existing projects and audits remain viewable.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.org_dependencies import requires
from app.api.site_audit_schemas import (
    CreateSeoProjectRequest,
    SeoProjectDetailOut,
    SeoProjectOut,
    SiteAuditDetailOut,
    SiteAuditPageOut,
    SiteAuditSettingsRequest,
    SiteAuditSummaryOut,
)
from app.config import Settings, get_settings
from app.db.models import SeoProject, SiteAudit
from app.db.session import get_session
from app.net_guard import is_public_url
from app.services import billing, quota
from app.services.permissions import AUDIT_RUN, PROJECT_CREATE, PROJECT_READ
from app.services.seo_projects import (
    DuplicateSeoProject,
    InvalidProjectDomain,
    SiteAuditAlreadyActive,
    already_tracked,
    count_org_projects,
    create_project_with_audit,
    get_org_audit,
    get_org_project,
    list_org_projects,
    normalize_project_domain,
    queue_site_audit,
)
from app.services.tenancy import OrgContext

router = APIRouter(prefix="/api/v1/seo-projects", tags=["seo-projects"])


def require_site_audit_enabled(settings: Annotated[Settings, Depends(get_settings)]) -> None:
    """404 the crawl-start route while no worker drains the queue.

    Mirrors ``backlink_routes.require_backlinks_enabled``: a kill switch that
    answers 404 (not 403) refuses even to confirm the surface is there. Applied
    only to ``POST /{project_id}/audits`` — the route whose sole job is to queue
    a crawl. Project creation is *not* gated this way (it suppresses the crawl
    via ``queue_audit`` instead), and the read routes stay open so existing
    projects and audits remain viewable while the feature is dark. See
    ``config.site_audit_enabled``.
    """

    if not settings.site_audit_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def _audit_summary(audit: SiteAudit) -> SiteAuditSummaryOut:
    return SiteAuditSummaryOut(
        id=audit.id,
        project_id=audit.project_id,
        status=audit.status,
        progress=audit.progress,
        current_step=audit.current_step,
        error=audit.error,
        page_limit=audit.page_limit,
        profile_id=audit.profile_id,
        js_rendering=audit.js_rendering,
        pages_discovered=audit.pages_discovered,
        pages_crawled=audit.pages_crawled,
        total_errors=audit.total_errors,
        total_warnings=audit.total_warnings,
        total_notices=audit.total_notices,
        health_score=audit.health_score,
        created_at=audit.created_at,
        updated_at=audit.updated_at,
        started_at=audit.started_at,
        completed_at=audit.completed_at,
    )


def _project_out(project: SeoProject) -> SeoProjectOut:
    latest_audit = max(project.audits, key=lambda audit: audit.created_at, default=None)
    return SeoProjectOut(
        id=project.id,
        name=project.name,
        domain=project.domain,
        created_at=project.created_at,
        updated_at=project.updated_at,
        latest_audit=_audit_summary(latest_audit) if latest_audit is not None else None,
    )


def _project_detail(project: SeoProject) -> SeoProjectDetailOut:
    project_out = _project_out(project)
    return SeoProjectDetailOut(
        **project_out.model_dump(),
        audits=[
            _audit_summary(audit)
            for audit in sorted(project.audits, key=lambda item: item.created_at, reverse=True)
        ],
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SeoProjectOut,
)
def create_seo_project(
    payload: CreateSeoProjectRequest,
    org: OrgContext = Depends(requires(PROJECT_CREATE)),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SeoProjectOut:
    try:
        domain = normalize_project_domain(payload.domain)
    except InvalidProjectDomain as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Site Audit is an authenticated surface, but its browser still fetches a
    # user-controlled URL. Apply the same public-host boundary as GEO discovery
    # before a project or queued job is persisted; the crawler will re-check
    # every request and redirect as defence in depth.
    if not is_public_url(domain.url):
        raise HTTPException(status_code=422, detail="domain host is not allowed")

    # A duplicate is answered before a quota is spent, and before a quota can
    # refuse. Both are 4xx and only one is actionable: "you already track this"
    # sends the customer to the project they have, while a 429 on the same
    # request would tell them to buy capacity they do not need. The service
    # re-checks this itself — see `already_tracked` — so this is an ordering
    # decision, not the guarantee.
    if already_tracked(session, user_id=org.require_user_id, domain_key=domain.key):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an SEO project for this domain already exists",
        )

    # Two allowances, and they are different kinds of thing (P7.6, ADR-45).
    # `projects` is a stock — how many you may hold at once — so it is measured
    # against the rows that exist and freed by deleting one. The first crawl is
    # an event, so it consumes the monthly `site_audits` flow, and only when a
    # crawl is actually queued: gating the count on `queue_audit` keeps
    # SITE_AUDIT_ENABLED=0 from silently charging for work nobody will do.
    org_id = org.require_org_id
    quota.check_stock(
        session,
        settings,
        org_id=org_id,
        metric=billing.METRIC_PROJECTS,
        current=count_org_projects(session, org_id),
    )
    if settings.site_audit_enabled:
        quota.consume(session, settings, org_id=org_id, metric=billing.METRIC_SITE_AUDITS)

    try:
        project = create_project_with_audit(
            session,
            user_id=org.require_user_id,
            context=org,
            domain=domain,
            name=payload.name,
            page_limit=payload.page_limit,
            profile_id=payload.profile_id,
            js_rendering=payload.js_rendering,
            queue_audit=settings.site_audit_enabled,
        )
    except DuplicateSeoProject as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an SEO project for this domain already exists",
        ) from exc

    return _project_out(project)


@router.get("", response_model=list[SeoProjectOut])
def read_seo_projects(
    org: OrgContext = Depends(requires(PROJECT_READ)),
    session: Session = Depends(get_session),
) -> list[SeoProjectOut]:
    return [_project_out(project) for project in list_org_projects(session, org.require_org_id)]


@router.get("/{project_id}", response_model=SeoProjectDetailOut)
def read_seo_project(
    project_id: uuid.UUID,
    org: OrgContext = Depends(requires(PROJECT_READ)),
    session: Session = Depends(get_session),
) -> SeoProjectDetailOut:
    project = get_org_project(session, org_id=org.require_org_id, project_id=project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="SEO project not found")
    return _project_detail(project)


@router.post(
    "/{project_id}/audits",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SiteAuditSummaryOut,
    dependencies=[Depends(require_site_audit_enabled)],
)
def create_site_audit(
    project_id: uuid.UUID,
    payload: SiteAuditSettingsRequest,
    org: OrgContext = Depends(requires(AUDIT_RUN)),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SiteAuditSummaryOut:
    project = get_org_project(session, org_id=org.require_org_id, project_id=project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="SEO project not found")

    # Metered after the project is resolved, so a 404 for another tenant's id
    # never spends this tenant's allowance — and after the flag check, which is
    # a route dependency, so a dark feature charges nobody.
    quota.consume(
        session,
        settings,
        org_id=org.require_org_id,
        metric=billing.METRIC_SITE_AUDITS,
    )

    try:
        audit = queue_site_audit(
            session,
            project=project,
            page_limit=payload.page_limit,
            profile_id=payload.profile_id,
            js_rendering=payload.js_rendering,
        )
    except SiteAuditAlreadyActive as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this SEO project already has an active audit",
        ) from exc

    return _audit_summary(audit)


@router.get(
    "/{project_id}/audits/{audit_id}",
    response_model=SiteAuditDetailOut,
)
def read_site_audit(
    project_id: uuid.UUID,
    audit_id: uuid.UUID,
    org: OrgContext = Depends(requires(PROJECT_READ)),
    session: Session = Depends(get_session),
) -> SiteAuditDetailOut:
    audit = get_org_audit(
        session,
        org_id=org.require_org_id,
        project_id=project_id,
        audit_id=audit_id,
    )
    if audit is None:
        raise HTTPException(status_code=404, detail="Site Audit not found")

    summary = _audit_summary(audit)
    return SiteAuditDetailOut(
        **summary.model_dump(),
        pages=[SiteAuditPageOut.model_validate(page) for page in audit.pages],
    )
