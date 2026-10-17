"""Poll standalone background jobs (``module_runs`` table — items 16–17).

Any ``job_kind`` (``kyc_extract``, ``geo_run``, ``serp_run``) enqueued via feature
POST routes can be polled here. Feature routes (``/ai-visibility/runs``,
``/serp/runs``) also expose poll + artifact slices; this path is the generic
status envelope only (Postgres read — not Redis).
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

router = APIRouter(prefix="/api/v1/background-jobs", tags=["background-jobs"])


@router.get("/{job_id}", response_model=ModuleRunOut)
def get_background_job(
    job_id: uuid.UUID,
    org: Annotated[OrgContext, Depends(requires(ANALYSIS_READ))],
    session: Annotated[Session, Depends(get_session)],
) -> ModuleRunOut:
    run = get_org_module_run(session, org_id=org.require_org_id, run_id=job_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return ModuleRunOut.model_validate(run)
