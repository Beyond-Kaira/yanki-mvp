"""Standalone SERP visibility runs — mod-3.

Enqueues ``job_kind=serp_run``. Poll here or via ``GET /background-jobs/{id}``;
fetch checks from the linked analysis shell.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.analysis_slices import build_serp_out
from app.api.kyc_schemas import ModuleRunOut
from app.api.org_dependencies import requires
from app.api.schemas import SerpVisibilityOut
from app.api.serp_schemas import CreateSerpRunRequest
from app.config import Settings, get_settings
from app.db.session import get_session
from app.jobs import redis_dispatch_queue
from app.jobs.module_kinds import JOB_KIND_SERP_RUN
from app.services import audit
from app.services.module_runs import ModuleRunValidationError, get_org_module_run, enqueue_module_run
from app.services.permissions import ANALYSIS_READ, ANALYSIS_RUN
from app.services.tenancy import OrgContext, readable_analysis

router = APIRouter(prefix="/api/v1/serp/runs", tags=["serp-runs"])


def _require_serp_run(run) -> None:
    if run.job_kind != JOB_KIND_SERP_RUN:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")


@router.post("", response_model=ModuleRunOut, status_code=status.HTTP_202_ACCEPTED)
def create_serp_run(
    body: CreateSerpRunRequest,
    org: Annotated[OrgContext, Depends(requires(ANALYSIS_RUN))],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ModuleRunOut:
    payload: dict = {"locale": body.locale}
    if body.queries is not None:
        payload["queries"] = body.queries

    user_id = org.require_user_id
    org_id = org.require_org_id

    try:
        run = enqueue_module_run(
            session,
            job_kind=JOB_KIND_SERP_RUN,
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
def get_serp_run(
    run_id: uuid.UUID,
    org: Annotated[OrgContext, Depends(requires(ANALYSIS_READ))],
    session: Annotated[Session, Depends(get_session)],
) -> ModuleRunOut:
    run = get_org_module_run(session, org_id=org.require_org_id, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    _require_serp_run(run)
    return ModuleRunOut.model_validate(run)


@router.get("/{run_id}/checks", response_model=SerpVisibilityOut)
def get_serp_run_checks(
    run_id: uuid.UUID,
    org: Annotated[OrgContext, Depends(requires(ANALYSIS_READ))],
    session: Annotated[Session, Depends(get_session)],
) -> SerpVisibilityOut:
    run = get_org_module_run(session, org_id=org.require_org_id, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    _require_serp_run(run)

    if run.linked_analysis_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="serp checks not ready")

    analysis = readable_analysis(session, run.linked_analysis_id, org)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="serp checks not found")

    serp_out = build_serp_out(analysis)
    if serp_out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="serp checks not ready")
    return serp_out
