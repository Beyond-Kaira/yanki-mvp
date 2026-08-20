"""Shared guards for guided analysis review-window edits."""

from __future__ import annotations

from app.db.models import Analysis
from app.services.analysis_run_mode import RUN_MODE_GUIDED, STATUS_AWAITING_REVIEW


class GuidedProfileConflictError(Exception):
    """The analysis is not in a state that accepts a guided edit."""

    def __init__(self, status: str, *, run_mode: str | None = None) -> None:
        self.status = status
        self.run_mode = run_mode
        super().__init__(f"analysis in status {status!r} cannot be edited")


class GuidedProfileValidationError(Exception):
    """The submitted guided edit failed validation."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def require_guided_review_window(analysis: Analysis) -> None:
    if analysis.run_mode != RUN_MODE_GUIDED:
        raise GuidedProfileConflictError(analysis.status, run_mode=analysis.run_mode)
    if analysis.status != STATUS_AWAITING_REVIEW:
        raise GuidedProfileConflictError(analysis.status, run_mode=analysis.run_mode)
