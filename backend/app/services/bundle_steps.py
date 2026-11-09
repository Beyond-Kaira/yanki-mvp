"""Thin bundle orchestrator flags for ``POST /analyses`` (mod-8)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BundleSteps(BaseModel):
    """Which monolith pipeline steps run. Omitted fields default to legacy (all on)."""

    kyc: bool = True
    geo: bool = True
    serp: bool = True


def bundle_steps_from_analysis(analysis) -> BundleSteps:  # noqa: ANN001
    raw = getattr(analysis, "bundle_steps", None)
    if not raw or not isinstance(raw, dict):
        return BundleSteps()
    return BundleSteps.model_validate(raw)


def bundle_steps_to_json(steps: BundleSteps | None) -> dict[str, Any] | None:
    if steps is None:
        return None
    return steps.model_dump()


DEFAULT_BUNDLE_STEPS = BundleSteps()
