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
from app.services.guided_prompts import PROMPT_SOURCE_GENERATED
from app.services.guided_review import (
    GuidedProfileValidationError,
    require_guided_review_window,
)

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

    require_guided_review_window(analysis)

    kyc = merge_kyc_patch(analysis.kyc, patch)
    try:
        prepare_user_edited_kyc(kyc, url=analysis.url)
    except PipelineError as exc:
        raise GuidedProfileValidationError(str(exc)) from exc

    analysis.kyc = kyc.model_dump()

    session.execute(delete(Prompt).where(Prompt.analysis_id == analysis.id))
    specs = prompts_step.generate_prompts(kyc, getattr(settings, "prompt_count", 10))
    for spec in specs:
        session.add(
            Prompt(
                analysis_id=analysis.id,
                text=spec.text,
                category=spec.category,
                source=PROMPT_SOURCE_GENERATED,
                locked=False,
            )
        )
    session.flush()
    session.refresh(analysis, attribute_names=["prompts"])
    return analysis
