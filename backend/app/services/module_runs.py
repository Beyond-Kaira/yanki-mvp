"""Enqueue and read standalone module runs (mod-6)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import BrandContext, ModuleRun
from app.jobs.module_kinds import MODULE_JOB_KINDS


class ModuleRunValidationError(Exception):
    """Caller-facing validation failure (422)."""


def get_org_module_run(
    session: Session,
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
) -> ModuleRun | None:
    return session.scalar(
        select(ModuleRun).where(
            ModuleRun.id == run_id,
            ModuleRun.org_id == org_id,
        )
    )


def enqueue_module_run(
    session: Session,
    *,
    job_kind: str,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    brand_context_id: uuid.UUID,
    payload: dict[str, Any] | None = None,
) -> ModuleRun:
    if job_kind not in MODULE_JOB_KINDS:
        raise ModuleRunValidationError(f"unknown job kind: {job_kind}")

    context = session.scalar(
        select(BrandContext).where(
            BrandContext.id == brand_context_id,
            BrandContext.org_id == org_id,
        )
    )
    if context is None:
        raise ModuleRunValidationError("brand context not found")

    run = ModuleRun(
        job_kind=job_kind,
        status="queued",
        org_id=org_id,
        created_by_user_id=user_id,
        brand_context_id=brand_context_id,
        payload=payload or {},
    )
    session.add(run)
    session.flush()
    return run
