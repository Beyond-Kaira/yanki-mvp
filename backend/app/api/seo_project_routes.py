"""Authenticated API for SEO projects and their independent Site Audit jobs."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.org_dependencies import get_org_context
from app.api.site_audit_schemas import (
    CreateSeoProjectRequest,
    SeoProjectDetailOut,
    SeoProjectOut,
    SiteAuditDetailOut,
    SiteAuditPageOut,
    SiteAuditSettingsRequest,
    SiteAuditSummaryOut,
)
from app.db.models import SeoProject, SiteAudit
from app.db.session import get_session
from app.net_guard import is_public_url
from app.services.seo_projects import (
    DuplicateSeoProject,
    InvalidProjectDomain,
    SiteAuditAlreadyActive,
    create_project_with_audit,
    get_org_audit,
    get_org_project,
    list_org_projects,
    normalize_project_domain,
    queue_site_audit,
)
from app.services.tenancy import OrgContext

router = APIRouter(prefix="/api/v1/seo-projects", tags=["seo-projects"])


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


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SeoProjectOut)
def create_seo_project(
    payload: CreateSeoProjectRequest,
    org: OrgContext = Depends(get_org_context),
    session: Session = Depends(get_session),
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
        )
    except DuplicateSeoProject as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an SEO project for this domain already exists",
        ) from exc

    return _project_out(project)


@router.get("", response_model=list[SeoProjectOut])
def read_seo_projects(
    org: OrgContext = Depends(get_org_context),
    session: Session = Depends(get_session),
) -> list[SeoProjectOut]:
    return [_project_out(project) for project in list_org_projects(session, org.require_org_id)]


@router.get("/{project_id}", response_model=SeoProjectDetailOut)
def read_seo_project(
    project_id: uuid.UUID,
    org: OrgContext = Depends(get_org_context),
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
)
def create_site_audit(
    project_id: uuid.UUID,
    payload: SiteAuditSettingsRequest,
    org: OrgContext = Depends(get_org_context),
    session: Session = Depends(get_session),
) -> SiteAuditSummaryOut:
    project = get_org_project(session, org_id=org.require_org_id, project_id=project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="SEO project not found")

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
    org: OrgContext = Depends(get_org_context),
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
