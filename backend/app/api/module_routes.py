"""Shared poll endpoint for standalone module runs (mod-6 / items 16–17).

Any ``job_kind`` (``kyc_extract``, ``geo_run``, ``serp_run``) enqueued via module
APIs can be polled here. Feature-specific routes (e.g. ``/ai-visibility/runs``)
may add artifact slices; this route is the generic status envelope.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.kyc_schemas import ModuleRunOut
from app.api.org_dependencies import requires
from app.db.session import get_session
from app.services.module_runs import get_org_module_run
from app.services.permissions import ANALYSIS_READ
from app.services.tenancy import OrgContext

router = APIRouter(prefix="/api/v1/module/runs", tags=["module-runs"])


@router.get("/{run_id}", response_model=ModuleRunOut)
def get_module_run(
    run_id: uuid.UUID,
    org: Annotated[OrgContext, Depends(requires(ANALYSIS_READ))],
    session: Annotated[Session, Depends(get_session)],
) -> ModuleRunOut:
    run = get_org_module_run(session, org_id=org.require_org_id, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    return ModuleRunOut.model_validate(run)
