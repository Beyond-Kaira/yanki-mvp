"""Run mode and status values for GEO analyses (ADR-50).

``quick`` — the existing one-shot path: all six pipeline steps run back-to-back.
``guided`` — profile phase (discovery → kyc → prompts) then pause for review;
measure phase (execute → scoring) starts on ``POST …/measure`` (later PR).
"""

from __future__ import annotations

from typing import Literal

RunMode = Literal["quick", "guided"]

RUN_MODE_QUICK: RunMode = "quick"
RUN_MODE_GUIDED: RunMode = "guided"

# Terminal-ish pause after the profile phase; not claimable by the queue worker.
STATUS_AWAITING_REVIEW = "awaiting_review"
