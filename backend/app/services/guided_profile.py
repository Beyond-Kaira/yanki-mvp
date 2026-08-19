"""Guided analysis profile edits (ADR-50 phase 2)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Analysis, Prompt
from app.pipeline import prompts as prompts_step
from app.pipeline.errors import PipelineError
from app.pipeline.kyc import KYC, prepare_user_edited_kyc
from app.services.analysis_run_mode import RUN_MODE_GUIDED, STATUS_AWAITING_REVIEW

# Fields a caller may change before measure. Deliberately excludes URL-derived
# facts we cannot re-verify without a re-crawl.
KYC_PATCH_FIELDS = frozenset(
    {
        "company",
        "description",
        "industry",
        "category",
        "aliases",
        "products",
        "services",
        "keywords",
        "use_cases",
        "locations",
        "competitors",
    }
)


class GuidedProfileConflictError(Exception):
    """The analysis is not in a state that accepts a profile edit."""

    def __init__(self, status: str, *, run_mode: str | None = None) -> None:
        self.status = status
        self.run_mode = run_mode
        super().__init__(f"analysis in status {status!r} cannot be edited")


class GuidedProfileValidationError(Exception):
    """The merged profile fails usability checks after sanitation."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def merge_kyc_patch(current: dict[str, Any] | None, patch: dict[str, Any]) -> KYC:
    """Apply ``patch`` onto the stored profile, keeping only allowlisted keys."""

    unknown = set(patch) - KYC_PATCH_FIELDS
    if unknown:
        raise GuidedProfileValidationError(f"fields not allowed: {', '.join(sorted(unknown))}")
    if not patch:
        raise GuidedProfileValidationError("at least one field is required")

    merged = dict(current or {})
    merged.update(patch)
    return KYC.model_validate(merged)


def patch_kyc_and_regenerate_prompts(
    session: Session,
    analysis: Analysis,
    patch: dict[str, Any],
    settings: Settings,
) -> Analysis:
    """Replace KYC fields, sanitize, and rebuild the deterministic prompt set."""

    if analysis.run_mode != RUN_MODE_GUIDED:
        raise GuidedProfileConflictError(analysis.status, run_mode=analysis.run_mode)
    if analysis.status != STATUS_AWAITING_REVIEW:
        raise GuidedProfileConflictError(analysis.status, run_mode=analysis.run_mode)

    kyc = merge_kyc_patch(analysis.kyc, patch)
    try:
        prepare_user_edited_kyc(kyc, url=analysis.url)
    except PipelineError as exc:
        raise GuidedProfileValidationError(str(exc)) from exc

    analysis.kyc = kyc.model_dump()

    session.execute(delete(Prompt).where(Prompt.analysis_id == analysis.id))
    specs = prompts_step.generate_prompts(kyc, getattr(settings, "prompt_count", 10))
    for spec in specs:
        session.add(Prompt(analysis_id=analysis.id, text=spec.text, category=spec.category))
    session.flush()
    session.refresh(analysis, attribute_names=["prompts"])
    return analysis
