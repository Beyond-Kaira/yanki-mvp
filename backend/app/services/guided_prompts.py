"""Guided prompt curation before measure (ADR-50 phase 3).

Each prompt carries ``source`` (``generated`` | ``edited`` | ``user``) and an
optional ``locked`` flag so a future UI can expose only editable rows while
preserving training lineage for a learned prompt generator.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Analysis, Prompt
from app.pipeline import prompts as prompts_step
from app.pipeline.kyc import KYC
from app.pipeline.prompts import BRAND_PROBE, CATEGORIES
from app.pipeline.sanitize import clean_str
from app.services.guided_review import (
    GuidedProfileValidationError,
    require_guided_review_window,
)

PROMPT_SOURCE_GENERATED = "generated"
PROMPT_SOURCE_EDITED = "edited"
PROMPT_SOURCE_USER = "user"

# How many net-new user prompts may appear in one guided set (cost guard).
USER_PROMPT_EXTRA = 3

ALLOWED_PROMPT_CATEGORIES = frozenset([*CATEGORIES, BRAND_PROBE, "custom"])

_MAX_PROMPT_TEXT = 500


@dataclass(frozen=True)
class PromptPatchItem:
    id: uuid.UUID | None
    text: str
    category: str


def max_prompts_for(settings: Settings) -> int:
    return int(getattr(settings, "prompt_count", 10)) + USER_PROMPT_EXTRA


def _validate_prompt_item(item: PromptPatchItem, *, brand_keys: list[str]) -> tuple[str, str]:
    text = clean_str(item.text, max_chars=_MAX_PROMPT_TEXT)
    category = clean_str(item.category, max_chars=40)
    if len(text) < 3:
        raise GuidedProfileValidationError("prompt text is too short")
    if not category or category not in ALLOWED_PROMPT_CATEGORIES:
        allowed = ", ".join(sorted(ALLOWED_PROMPT_CATEGORIES))
        raise GuidedProfileValidationError(f"prompt category must be one of: {allowed}")
    if category != BRAND_PROBE and prompts_step.leaks_brand(text, brand_keys):
        raise GuidedProfileValidationError(
            "category prompts must not name the brand being measured"
        )
    return text, category


def _next_source(existing: Prompt, text: str, category: str) -> str:
    if existing.locked:
        return existing.source
    if existing.source == PROMPT_SOURCE_USER:
        return PROMPT_SOURCE_USER
    if existing.text == text and existing.category == category:
        return existing.source
    if existing.source == PROMPT_SOURCE_GENERATED:
        return PROMPT_SOURCE_EDITED
    return PROMPT_SOURCE_EDITED


def patch_analysis_prompts(
    session: Session,
    analysis: Analysis,
    items: list[PromptPatchItem],
    settings: Settings,
) -> Analysis:
    """Replace the editable prompt set while preserving locked rows and lineage."""

    require_guided_review_window(analysis)

    if not items:
        raise GuidedProfileValidationError("at least one prompt is required")

    max_total = max_prompts_for(settings)
    if len(items) > max_total:
        raise GuidedProfileValidationError(
            f"at most {max_total} prompts are allowed ({USER_PROMPT_EXTRA} may be user-added)"
        )

    new_items = [item for item in items if item.id is None]
    if len(new_items) > USER_PROMPT_EXTRA:
        raise GuidedProfileValidationError(f"at most {USER_PROMPT_EXTRA} new prompts may be added")

    kyc = KYC.model_validate(analysis.kyc or {})
    brand_keys = prompts_step.brand_keys(kyc)
    existing = {prompt.id: prompt for prompt in analysis.prompts}
    locked = {prompt.id: prompt for prompt in analysis.prompts if prompt.locked}

    kept_ids: set[uuid.UUID] = set()
    seen_text: set[str] = set()

    for item in items:
        text, category = _validate_prompt_item(item, brand_keys=brand_keys)
        folded = text.casefold()
        if folded in seen_text:
            raise GuidedProfileValidationError("duplicate prompt text")
        seen_text.add(folded)

        if item.id is None:
            session.add(
                Prompt(
                    analysis_id=analysis.id,
                    text=text,
                    category=category,
                    source=PROMPT_SOURCE_USER,
                    locked=False,
                )
            )
            continue

        row = existing.get(item.id)
        if row is None or row.analysis_id != analysis.id:
            raise GuidedProfileValidationError(f"unknown prompt id: {item.id}")

        if row.locked:
            if row.text != text or row.category != category:
                raise GuidedProfileValidationError("locked prompts cannot be edited")
        else:
            row.source = _next_source(row, text, category)
            row.text = text
            row.category = category

        kept_ids.add(row.id)

    for locked_id, locked_row in locked.items():
        if locked_id not in kept_ids:
            raise GuidedProfileValidationError("locked prompts must be included unchanged")
        if locked_row.text.casefold() not in seen_text:
            raise GuidedProfileValidationError("locked prompts must be included unchanged")

    for prompt_id, prompt in existing.items():
        if prompt_id not in kept_ids and not prompt.locked:
            session.delete(prompt)

    session.flush()
    session.refresh(analysis, attribute_names=["prompts"])

    if len(analysis.prompts) < 1:
        raise GuidedProfileValidationError("at least one prompt is required")
    if len(analysis.prompts) > max_total:
        raise GuidedProfileValidationError(f"at most {max_total} prompts are allowed")

    return analysis
