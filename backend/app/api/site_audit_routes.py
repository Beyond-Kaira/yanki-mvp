"""Standalone Site Audit run API (mod-11) — thin alias over SEO project audits."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.org_dependencies import requires
from app.api.seo_project_routes import _audit_summary, require_site_audit_enabled
from app.api.site_audit_schemas import (
    SiteAuditDetailOut,
    SiteAuditPageOut,
    SiteAuditSettingsRequest,
    SiteAuditSummaryOut,
)
from app.config import Settings, get_settings
from app.db.session import get_session
from app.services import billing, quota
from app.services.permissions import AUDIT_RUN, PROJECT_READ
from app.services.seo_projects import (
    SiteAuditAlreadyActive,
    get_org_audit,
    get_org_project,
    queue_site_audit,
)
from app.services.tenancy import OrgContext

router = APIRouter(prefix="/api/v1/site-audit", tags=["site-audit"])


class CreateSiteAuditRunRequest(SiteAuditSettingsRequest):
    project_id: uuid.UUID


@router.post(
    "/runs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SiteAuditSummaryOut,
    dependencies=[Depends(require_site_audit_enabled)],
)
def create_site_audit_run(
    body: CreateSiteAuditRunRequest,
    org: Annotated[OrgContext, Depends(requires(AUDIT_RUN))],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SiteAuditSummaryOut:
    project = get_org_project(session, org_id=org.require_org_id, project_id=body.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="SEO project not found")

    quota.consume(
        session,
        settings,
        org_id=org.require_org_id,
        metric=billing.METRIC_SITE_AUDITS,
        context=org,
    )
    try:
        audit = queue_site_audit(
            session,
            project=project,
            page_limit=body.page_limit,
            profile_id=body.profile_id,
            js_rendering=body.js_rendering,
            settings=settings,
        )
    except SiteAuditAlreadyActive as exc:
        raise HTTPException(status_code=409, detail="active audit already exists") from exc
    return _audit_summary(audit)


@router.get("/runs/{audit_id}", response_model=SiteAuditDetailOut)
def read_site_audit_run(
    audit_id: uuid.UUID,
    project_id: Annotated[uuid.UUID, Query(description="SEO project that owns the audit")],
    org: Annotated[OrgContext, Depends(requires(PROJECT_READ))],
    session: Annotated[Session, Depends(get_session)],
) -> SiteAuditDetailOut:
    audit = get_org_audit(
        session,
        org_id=org.require_org_id,
        project_id=project_id,
        audit_id=audit_id,
    )
    if audit is None:
        raise HTTPException(status_code=404, detail="site audit not found")
    summary = _audit_summary(audit)
    return SiteAuditDetailOut(
        **summary.model_dump(),
        pages=[SiteAuditPageOut.model_validate(page) for page in audit.pages],
    )
