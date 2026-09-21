"""Standalone brand context (KYC) profiles — decoupled from analysis_id (mod-5).

Creating or updating a profile must not enqueue GEO, SERP, or any other module
run (ADR-52). Optional URL extraction runs discovery + KYC inline on POST only.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.kyc_schemas import (
    BrandContextOut,
    CreateBrandContextRequest,
    ExtractBrandContextRequest,
    ModuleRunOut,
    PatchBrandContextRequest,
)
from app.jobs.module_kinds import JOB_KIND_KYC_EXTRACT
from app.api.org_dependencies import requires
from app.config import Settings, get_settings
from app.db.session import get_session
from app.services import audit
from app.services.brand_contexts import (
    BrandContextValidationError,
    create_brand_context,
    get_org_brand_context,
    patch_brand_context,
)
from app.services.module_runs import ModuleRunValidationError, enqueue_module_run
from app.services.guided_profile import GuidedProfileValidationError
from app.services.permissions import ANALYSIS_READ, ANALYSIS_RUN
from app.services.tenancy import OrgContext

router = APIRouter(prefix="/api/v1/kyc/profiles", tags=["kyc-profiles"])


def _out(context) -> BrandContextOut:
    return BrandContextOut.model_validate(context)

@router.post("", response_model=BrandContextOut, status_code=status.HTTP_201_CREATED)
def create_profile(
    body: CreateBrandContextRequest,
    org: Annotated[OrgContext, Depends(requires(ANALYSIS_RUN))],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BrandContextOut:
    try:
        context = create_brand_context(
            session,
            org_id=org.org_id,
            user_id=org.user_id,
            payload=body.model_dump(exclude_unset=True),
            settings=settings,
        )
    except BrandContextValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    audit.emit(
        session,
        action="brand_context:create",
        context=org,
        actor_type="user",
        actor_id=org.user_id,
        entity_type="brand_context",
        entity_id=context.id,
        after={"brand": context.brand, "source_url": context.source_url},
    )
    session.commit()
    return _out(context)


@router.get("/{profile_id}", response_model=BrandContextOut)
def read_profile(
    profile_id: uuid.UUID,
    org: Annotated[OrgContext, Depends(requires(ANALYSIS_READ))],
    session: Annotated[Session, Depends(get_session)],
) -> BrandContextOut:
    context = get_org_brand_context(session, org_id=org.org_id, context_id=profile_id)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")
    return _out(context)


@router.patch("/{profile_id}", response_model=BrandContextOut)
def update_profile(
    profile_id: uuid.UUID,
    body: PatchBrandContextRequest,
    org: Annotated[OrgContext, Depends(requires(ANALYSIS_RUN))],
    session: Annotated[Session, Depends(get_session)],
) -> BrandContextOut:
    context = get_org_brand_context(session, org_id=org.org_id, context_id=profile_id)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")

    patch = body.model_dump(exclude_unset=True)
    before = {"brand": context.brand, "category": context.category}
    try:
        context = patch_brand_context(session, context=context, patch=patch)
    except (BrandContextValidationError, GuidedProfileValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    audit.emit(
        session,
        action="brand_context:patch",
        context=org,
        actor_type="user",
        actor_id=org.user_id,
        entity_type="brand_context",
        entity_id=context.id,
        before=before,
        after={"brand": context.brand, "category": context.category},
    )
    session.commit()
    return _out(context)


@router.post(
    "/{profile_id}/extract",
    response_model=ModuleRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_profile_extract(
    profile_id: uuid.UUID,
    body: ExtractBrandContextRequest,
    org: Annotated[OrgContext, Depends(requires(ANALYSIS_RUN))],
    session: Annotated[Session, Depends(get_session)],
) -> ModuleRunOut:
    context = get_org_brand_context(session, org_id=org.org_id, context_id=profile_id)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")

    payload: dict = {}
    if body.source_url is not None:
        payload["source_url"] = body.source_url
    elif context.source_url:
        payload["source_url"] = context.source_url
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="source_url is required",
        )

    try:
        run = enqueue_module_run(
            session,
            job_kind=JOB_KIND_KYC_EXTRACT,
            org_id=org.org_id,
            user_id=org.user_id,
            brand_context_id=context.id,
            payload=payload,
        )
    except ModuleRunValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    audit.emit(
        session,
        action="module_run:enqueue",
        context=org,
        actor_type="user",
        actor_id=org.user_id,
        entity_type="module_run",
        entity_id=run.id,
        after={"job_kind": run.job_kind, "brand_context_id": str(context.id)},
    )
    session.commit()
    return ModuleRunOut.model_validate(run)
