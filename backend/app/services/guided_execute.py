"""Enqueue guided measure phase after profile review (ADR-50 phase 4)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Analysis
from app.pipeline import kyc as kyc_step
from app.pipeline.runner import PROMPTS_DONE_PROGRESS
from app.services.guided_review import (
    GuidedProfileConflictError,
    GuidedProfileValidationError,
    require_guided_review_window,
)


def request_execute_prompts_and_score(
    session: Session,
    analysis: Analysis,
    settings: Settings,
) -> Analysis:
    """Validate a guided run and re-queue it for execute→scoring only."""

    _ = settings
    require_guided_review_window(analysis)

    if (analysis.kind or "mvp") != "mvp":
        raise GuidedProfileConflictError(analysis.status, run_mode=analysis.run_mode)

    if not analysis.prompts:
        raise GuidedProfileValidationError("at least one prompt is required")

    kyc = kyc_step.KYC.model_validate(analysis.kyc)
    try:
        kyc_step.require_usable(kyc)
    except kyc_step.PipelineError as exc:
        raise GuidedProfileValidationError(str(exc)) from exc

    analysis.status = "queued"
    analysis.progress = PROMPTS_DONE_PROGRESS
    analysis.current_step = None
    analysis.error = None
    session.flush()
    return analysis
