"""Transparent page and audit health scoring for Site Audit."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def is_scorable_page(status_code: int, issues: list[dict[str, Any]]) -> bool:
    """Robots-blocked URLs are discovered, but are not scoreable crawl results."""

    return not any(issue.get("code") == "blocked_by_robots" for issue in issues)


def page_health_score(status_code: int, issues: list[dict[str, Any]]) -> int | None:
    if not is_scorable_page(status_code, issues):
        return None
    if status_code == 0 or status_code >= 400:
        return 0

    errors = sum(issue.get("severity") == "error" for issue in issues)
    warnings = sum(issue.get("severity") == "warning" for issue in issues)
    return max(0, 100 - errors * 15 - warnings * 5)


def audit_health_score(page_scores: Iterable[int | None]) -> int | None:
    scores = [score for score in page_scores if score is not None]
    return round(sum(scores) / len(scores)) if scores else None
