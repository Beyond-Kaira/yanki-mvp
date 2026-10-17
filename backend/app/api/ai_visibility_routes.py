"""Standalone AI visibility (GEO) runs — mod-4.

Enqueues ``job_kind=geo_run`` module jobs. Does not start discovery, KYC extract,
or SERP. Poll run status here; fetch GEO artifact from the linked analysis slice.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.ai_visibility_schemas import CreateAiVisibilityRunRequest
from app.api.analysis_slices import build_geo_out
from app.api.kyc_schemas import ModuleRunOut
from app.api.org_dependencies import requires
from app.api.schemas import GeoOut
from app.config import Settings, get_settings
from app.db.models import Analysis
from app.db.session import get_session
from app.jobs import redis_dispatch_queue
from app.jobs.module_kinds import JOB_KIND_GEO_RUN
from app.services import audit
from app.services.module_runs import ModuleRunValidationError, get_org_module_run, enqueue_module_run
from app.services.permissions import ANALYSIS_READ, ANALYSIS_RUN
from app.services.tenancy import OrgContext, readable_analysis

router = APIRouter(prefix="/api/v1/ai-visibility/runs", tags=["ai-visibility-runs"])


def _require_geo_run(run) -> None:
    if run.job_kind != JOB_KIND_GEO_RUN:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")


@router.post("", response_model=ModuleRunOut, status_code=status.HTTP_202_ACCEPTED)
def create_ai_visibility_run(
    body: CreateAiVisibilityRunRequest,
    org: Annotated[OrgContext, Depends(requires(ANALYSIS_RUN))],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ModuleRunOut:
    payload = {
        "mode": body.mode,
        "prompts": [{"text": p.text, "category": p.category} for p in body.prompts],
    }

    user_id = org.require_user_id
    org_id = org.require_org_id

    try:
        run = enqueue_module_run(
            session,
            job_kind=JOB_KIND_GEO_RUN,
            org_id=org_id,
            user_id=user_id,
            brand_context_id=body.brand_context_id,
            payload=payload,
        )
    except ModuleRunValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    audit.emit(
        session,
        action="module_run:enqueue",
        context=org,
        actor_type="user",
        actor_id=user_id,
        entity_type="module_run",
        entity_id=run.id,
        after={"job_kind": run.job_kind, "brand_context_id": str(body.brand_context_id)},
    )
    session.commit()
    redis_dispatch_queue.notify_module_run_enqueued(run.id, settings)
    return ModuleRunOut.model_validate(run)


@router.get("/{run_id}", response_model=ModuleRunOut)
def get_ai_visibility_run(
    run_id: uuid.UUID,
    org: Annotated[OrgContext, Depends(requires(ANALYSIS_READ))],
    session: Annotated[Session, Depends(get_session)],
) -> ModuleRunOut:
    run = get_org_module_run(session, org_id=org.require_org_id, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    _require_geo_run(run)
    return ModuleRunOut.model_validate(run)


@router.get("/{run_id}/geo", response_model=GeoOut)
def get_ai_visibility_geo_artifact(
    run_id: uuid.UUID,
    org: Annotated[OrgContext, Depends(requires(ANALYSIS_READ))],
    session: Annotated[Session, Depends(get_session)],
) -> GeoOut:
    run = get_org_module_run(session, org_id=org.require_org_id, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    _require_geo_run(run)

    if run.linked_analysis_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="geo artifact not ready")

    analysis = session.get(Analysis, run.linked_analysis_id)
    if analysis is None or not readable_analysis(org, analysis):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="geo artifact not found")

    return build_geo_out(analysis)
