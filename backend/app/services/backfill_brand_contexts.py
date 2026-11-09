"""Map legacy ``analyses.kyc`` snapshots to ``brand_contexts`` (mod-1-s3 / action 18)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Analysis, BrandContext
from app.pipeline.kyc import KYC


def _domain_from_url(url: str) -> str | None:
    host = (urlparse(url).hostname or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def fields_from_analysis_kyc(analysis: Analysis) -> dict[str, Any] | None:
    """Build BrandContext column values from an analysis row, or None if not mappable."""

    raw = analysis.kyc
    if not raw or not isinstance(raw, dict):
        return None

    company = (raw.get("company") or analysis.brand or "").strip()
    if not company:
        return None

    try:
        kyc = KYC.model_validate({**raw, "company": company})
    except ValidationError:
        return None

    category = (kyc.category or analysis.category or "").strip() or None
    return {
        "org_id": analysis.org_id,
        "created_by_user_id": analysis.created_by_user_id,
        "source_url": analysis.url,
        "brand": kyc.company,
        "domain": _domain_from_url(analysis.url),
        "locale": (analysis.lang or "en").strip() or "en",
        "category": category,
        "competitors": list(kyc.competitors or []),
        "profile": kyc.model_dump(),
    }


@dataclass(frozen=True)
class BackfillStats:
    scanned: int
    linked: int
    skipped: int


def backfill_analysis_brand_contexts(
    session: Session,
    *,
    org_id: uuid.UUID | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> BackfillStats:
    """Create BrandContext rows for analyses with ``kyc`` but no ``brand_context_id``."""

    stmt = (
        select(Analysis)
        .where(
            Analysis.brand_context_id.is_(None),
            Analysis.kyc.isnot(None),
        )
        .order_by(Analysis.created_at)
    )
    if org_id is not None:
        stmt = stmt.where(Analysis.org_id == org_id)
    if limit is not None:
        stmt = stmt.limit(limit)

    scanned = linked = skipped = 0
    for analysis in session.scalars(stmt):
        scanned += 1
        fields = fields_from_analysis_kyc(analysis)
        if fields is None:
            skipped += 1
            continue
        if dry_run:
            linked += 1
            continue
        ctx = BrandContext(**fields)
        session.add(ctx)
        session.flush()
        analysis.brand_context_id = ctx.id
        linked += 1

    return BackfillStats(scanned=scanned, linked=linked, skipped=skipped)
