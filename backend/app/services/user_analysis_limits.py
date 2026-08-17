"""Interim per-user analysis stock limit (temporary until plan/org billing ships).

Hardcoded — no env flag, no billing integration. Replace when user plans,
organizational accounts and invites land.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Analysis
from app.services.analyses import LISTABLE_KINDS

# Temporary gate — not configurable via deploy/.env (see canvas / P0 spec).
USER_ANALYSIS_LIMIT = 5

METRIC_USER_ANALYSES = "user_analyses"

# Failed rows are auto-purged and excluded; see worker + delete path (P4).
_ACTIVE_STATUSES = ("queued", "running", "done")


class UserAnalysisLimitExceeded(RuntimeError):
    """The user already holds the maximum number of active analyses."""

    def __init__(self, used: int, limit: int = USER_ANALYSIS_LIMIT) -> None:
        super().__init__(f"{METRIC_USER_ANALYSES} limit exhausted ({used}/{limit})")
        self.metric = METRIC_USER_ANALYSES
        self.used = used
        self.limit = limit


def count_active_user_analyses(session: Session, user_id: uuid.UUID) -> int:
    """How many analyses this user currently holds against the stock limit."""

    return int(
        session.scalar(
            select(func.count())
            .select_from(Analysis)
            .where(
                Analysis.created_by_user_id == user_id,
                Analysis.kind.in_(LISTABLE_KINDS),
                Analysis.status.in_(_ACTIVE_STATUSES),
            )
        )
        or 0
    )


def enforce_user_analysis_limit(session: Session, user_id: uuid.UUID) -> None:
    """Refuse when the user already holds USER_ANALYSIS_LIMIT active analyses."""

    used = count_active_user_analyses(session, user_id)
    if used >= USER_ANALYSIS_LIMIT:
        raise UserAnalysisLimitExceeded(used)
