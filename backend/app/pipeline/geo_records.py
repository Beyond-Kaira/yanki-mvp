"""Persist Kaira-style audit records as columnar ``geo_records`` rows.

Also aggregates per-analysis ``citation_summary`` from those records.
``responses.audit`` remains the opaque JSON twin; this module is the queryable
copy.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.db.models import GeoRecord


def _parse_generated_at(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _as_list(value: Any) -> list[Any] | None:
    """LLM sometimes returns a bare string where the schema expects a list."""
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [value]


def _as_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    return None


def geo_record_from_audit(
    record: Mapping[str, Any],
    *,
    analysis_id: uuid.UUID,
    response_id: uuid.UUID,
) -> GeoRecord:
    """Map one measured/simulated audit dict onto a ``GeoRecord`` ORM row."""
    return GeoRecord(
        analysis_id=analysis_id,
        response_id=response_id,
        brand=str(record.get("brand") or ""),
        sector=record.get("sector") or None,
        prompt=str(record.get("prompt") or ""),
        prompt_group=record.get("prompt_group") or None,
        intent=record.get("intent") or None,
        measurement_mode=record.get("measurement_mode") or None,
        search_provider=record.get("search_provider") or None,
        search_results=record.get("search_results"),
        search_visibility=_as_dict(record.get("search_visibility")),
        grounded_answer=record.get("grounded_answer") or None,
        simulated_answer=record.get("simulated_answer") or None,
        mentioned=record.get("mentioned") if "mentioned" in record else None,
        rank_position=record.get("rank_position"),
        mention_context=record.get("mention_context") or None,
        competitors=_as_list(record.get("competitors")),
        answer_summary=record.get("answer_summary") or None,
        recommendation_reasoning=record.get("recommendation_reasoning") or None,
        reasoning_trace=_as_dict(record.get("reasoning_trace")),
        citations=_as_list(record.get("citations")),
        citation_metrics=_as_dict(record.get("citation_metrics")),
        visibility_drivers=_as_dict(record.get("visibility_drivers")),
        visibility_gaps=_as_dict(record.get("visibility_gaps")),
        trust_signals=_as_list(record.get("trust_signals")),
        entities_associated_with_brand=_as_list(
            record.get("entities_associated_with_brand")
        ),
        sentiment=record.get("sentiment") or None,
        content_improvement_opportunities=_as_list(
            record.get("content_improvement_opportunities")
        ),
        model=record.get("model") or None,
        generated_at=_parse_generated_at(record.get("generated_at")),
        error=bool(record.get("error")) if "error" in record else None,
        schema_version=record.get("schema_version") or None,
        owned_domains=_as_list(record.get("owned_domains")),
    )


def aggregate_citation_summary(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Roll up citation_metrics across prompt records for ``analyses``."""
    if not records:
        return {
            "record_count": 0,
            "cite_rate": 0.0,
            "owned_rate": 0.0,
            "earned_rate": 0.0,
            "avg_citations": 0.0,
            "competitor_citation_share": {},
        }

    cited = 0
    owned = 0
    earned = 0
    total_citations = 0
    share: dict[str, int] = {}

    for record in records:
        metrics = record.get("citation_metrics") or {}
        if metrics.get("target_brand_cited"):
            cited += 1
        if metrics.get("owned_media_cited"):
            owned += 1
        if metrics.get("earned_media_cited"):
            earned += 1
        total_citations += int(metrics.get("total_citations") or 0)
        for name, count in (metrics.get("competitor_citation_share") or {}).items():
            key = str(name)
            share[key] = share.get(key, 0) + int(count)

    n = len(records)
    top_share = dict(sorted(share.items(), key=lambda item: (-item[1], item[0]))[:20])
    return {
        "record_count": n,
        "cite_rate": round(cited / n, 4),
        "owned_rate": round(owned / n, 4),
        "earned_rate": round(earned / n, 4),
        "avg_citations": round(total_citations / n, 4),
        "competitor_citation_share": top_share,
    }
