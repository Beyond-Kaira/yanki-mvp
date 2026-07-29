"""
Generate structured GEO interventions from audit records and the intervention library.

Pipeline:
    1. load_library()           — read intervention templates JSON
    2. match_record()           — evaluate triggers per audit record
    3. aggregate_interventions() — dedupe and rank across multiple records (brand-level)

Triggers (all must pass when specified):
    - gap_categories: at least one category has non-empty visibility_gaps
    - metric_conditions: nested field equality checks on the audit record
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

DEFAULT_LIBRARY = (
    Path(__file__).resolve().parents[1] / "data/intervention_library.json"
)
DEFAULT_DATASET = None
DEFAULT_OUTPUT = None

GAP_CATEGORIES = [
    "low_discoverability",
    "weak_ranking",
    "category_mismatch",
    "weak_trust_signals",
    "weak_feature_association",
    "competitor_dominance",
    "content_gap",
    "international_positioning_gap",
    "ux_positioning_gap",
    "reputation_gap",
]


@dataclass
class MatchedIntervention:
    """A library template matched to a specific audit record."""

    template_id: str
    title: str
    description: str
    label: str
    applicability_score: int
    geo_impact_score: int
    priority_score: float
    expected_outcome: str
    geo_theory_basis: str
    triggered_by: dict[str, Any] = field(default_factory=dict)


def load_library(path: Optional[Path] = None) -> dict[str, Any]:
    library_path = path or DEFAULT_LIBRARY
    with open(library_path, "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def load_dataset(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _get_nested_value(record: dict[str, Any], dotted_key: str) -> Any:
    current: Any = record
    for part in dotted_key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _normalize_gaps(record: dict[str, Any]) -> dict[str, list[str]]:
    gaps = record.get("visibility_gaps", {})
    if isinstance(gaps, list):
        return {"low_discoverability": gaps}
    normalized = {category: [] for category in GAP_CATEGORIES}
    if isinstance(gaps, dict):
        for category in GAP_CATEGORIES:
            items = gaps.get(category, []) or []
            normalized[category] = items if isinstance(items, list) else [str(items)]
    return normalized


def _active_gap_categories(record: dict[str, Any]) -> list[str]:
    gaps = _normalize_gaps(record)
    return [category for category, items in gaps.items() if items]


def _gap_claims_for_categories(record: dict[str, Any], categories: list[str]) -> list[str]:
    gaps = _normalize_gaps(record)
    claims: list[str] = []
    for category in categories:
        claims.extend(gaps.get(category, []))
    return claims


def _metric_value_for_condition(record: dict[str, Any], key: str, value: Any) -> Any:
    if key in record:
        return record.get(key)
    return _get_nested_value(record, key)


def _metric_conditions_match(record: dict[str, Any], conditions: dict[str, Any]) -> bool:
    if not conditions:
        return True

    for key, expected in conditions.items():
        actual = _metric_value_for_condition(record, key, expected)
        if actual != expected:
            return False
    return True


def _gap_categories_match(record: dict[str, Any], categories: list[str]) -> bool:
    if not categories:
        return True
    active = set(_active_gap_categories(record))
    return bool(active.intersection(categories))


def _owned_domain_for_brand(record: dict[str, Any]) -> str:
    owned = record.get("owned_domains") or []
    if owned:
        return owned[0]
    return "owned domain"


def _render_template(text: str, record: dict[str, Any]) -> str:
    brand = record.get("brand", "")
    search_visibility = record.get("search_visibility", {})
    replacements = {
        "brand": brand,
        "prompt": record.get("prompt", ""),
        "prompt_group": record.get("prompt_group", ""),
        "owned_domain": _owned_domain_for_brand(record),
        "brand_best_rank": str(search_visibility.get("brand_best_rank", "N/A")),
    }
    rendered = text
    for key, value in replacements.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def _priority_score(geo_impact_score: int, applicability_score: int) -> float:
    if applicability_score <= 0:
        return float(geo_impact_score)
    return round(geo_impact_score / applicability_score, 3)


def _build_evidence_refs(record: dict[str, Any], matched_categories: list[str]) -> list[str]:
    refs: list[str] = []
    visibility = record.get("search_visibility", {})
    metrics = record.get("citation_metrics", {})

    if visibility.get("owned_domain_in_results") is False:
        refs.append("search_visibility.owned_domain_in_results=false")
    if visibility.get("brand_in_results") is not None:
        refs.append(f"search_visibility.brand_in_results={visibility.get('brand_in_results')}")
    if visibility.get("brand_best_rank"):
        refs.append(f"search_visibility.brand_best_rank={visibility.get('brand_best_rank')}")
    if record.get("mentioned") is not None:
        refs.append(f"mentioned={record.get('mentioned')}")
    if metrics.get("target_brand_cited") is not None:
        refs.append(f"citation_metrics.target_brand_cited={metrics.get('target_brand_cited')}")
    if record.get("mention_context"):
        refs.append(f"mention_context={record.get('mention_context')}")

    for claim in _gap_claims_for_categories(record, matched_categories)[:2]:
        refs.append(f"visibility_gaps: {claim[:120]}")

    return refs


def template_matches_record(template: dict[str, Any], record: dict[str, Any]) -> bool:
    triggers = template.get("triggers", {})
    gap_categories = triggers.get("gap_categories", [])
    metric_conditions = triggers.get("metric_conditions", {})

    has_gap_trigger = bool(gap_categories)
    has_metric_trigger = bool(metric_conditions)

    if not has_gap_trigger and not has_metric_trigger:
        return False

    if has_gap_trigger and not _gap_categories_match(record, gap_categories):
        return False

    if has_metric_trigger and not _metric_conditions_match(record, metric_conditions):
        return False

    return True


def match_record(
    record: dict[str, Any],
    library: Optional[dict[str, Any]] = None,
) -> list[MatchedIntervention]:
    library = library or load_library()
    matches: list[MatchedIntervention] = []

    for template in library.get("templates", []):
        if not template_matches_record(template, record):
            continue

        triggers = template.get("triggers", {})
        gap_categories = triggers.get("gap_categories", [])
        active_matched = [
            category for category in gap_categories if category in _active_gap_categories(record)
        ]

        applicability = int(template["applicability_score"])
        geo_impact = int(template["geo_impact_score"])

        matches.append(
            MatchedIntervention(
                template_id=template["id"],
                title=_render_template(template["title"], record),
                description=_render_template(template["description"], record),
                label=template["label"],
                applicability_score=applicability,
                geo_impact_score=geo_impact,
                priority_score=_priority_score(geo_impact, applicability),
                expected_outcome=template.get("expected_outcome", ""),
                geo_theory_basis=template.get("geo_theory_basis", ""),
                triggered_by={
                    "gap_categories": active_matched or gap_categories,
                    "gap_claims": _gap_claims_for_categories(record, active_matched or gap_categories),
                    "evidence": _build_evidence_refs(record, active_matched or gap_categories),
                    "prompt": record.get("prompt"),
                    "prompt_group": record.get("prompt_group"),
                },
            )
        )

    matches.sort(key=lambda item: (-item.priority_score, item.applicability_score, item.title))
    return matches


def _intervention_to_dict(intervention: MatchedIntervention) -> dict[str, Any]:
    return {
        "id": intervention.template_id,
        "title": intervention.title,
        "description": intervention.description,
        "label": intervention.label,
        "applicability_score": intervention.applicability_score,
        "geo_impact_score": intervention.geo_impact_score,
        "priority_score": intervention.priority_score,
        "expected_outcome": intervention.expected_outcome,
        "geo_theory_basis": intervention.geo_theory_basis,
        "triggered_by": intervention.triggered_by,
    }


def analyze_record(
    record: dict[str, Any],
    library: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    interventions = match_record(record, library=library)
    return {
        "brand": record.get("brand"),
        "prompt": record.get("prompt"),
        "prompt_group": record.get("prompt_group"),
        "mentioned": record.get("mentioned"),
        "intervention_count": len(interventions),
        "interventions": [_intervention_to_dict(item) for item in interventions],
    }


def aggregate_interventions(
    record_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deduplicate interventions across records; merge evidence and boost priority."""
    aggregated: dict[str, dict[str, Any]] = {}

    for result in record_results:
        for intervention in result.get("interventions", []):
            template_id = intervention["id"]
            if template_id not in aggregated:
                aggregated[template_id] = deepcopy(intervention)
                aggregated[template_id]["trigger_count"] = 1
                aggregated[template_id]["triggered_prompts"] = [result.get("prompt")]
                aggregated[template_id]["triggered_by"]["record_prompts"] = [result.get("prompt")]
                continue

            existing = aggregated[template_id]
            existing["trigger_count"] += 1
            existing["triggered_prompts"].append(result.get("prompt"))
            existing["triggered_by"]["record_prompts"].append(result.get("prompt"))

            for claim in intervention["triggered_by"].get("gap_claims", []):
                if claim not in existing["triggered_by"].setdefault("gap_claims", []):
                    existing["triggered_by"]["gap_claims"].append(claim)

            for evidence in intervention["triggered_by"].get("evidence", []):
                if evidence not in existing["triggered_by"].setdefault("evidence", []):
                    existing["triggered_by"]["evidence"].append(evidence)

            boost = min(0.5, 0.1 * (existing["trigger_count"] - 1))
            existing["priority_score"] = round(existing["priority_score"] + boost, 3)

    items = list(aggregated.values())
    items.sort(key=lambda item: (-item["priority_score"], item["applicability_score"], item["title"]))
    return items


def _label_breakdown(interventions: list[dict[str, Any]]) -> dict[str, int]:
    breakdown: dict[str, int] = {}
    for intervention in interventions:
        label = intervention["label"]
        breakdown[label] = breakdown.get(label, 0) + 1
    return dict(sorted(breakdown.items(), key=lambda item: item[0]))


def _applicability_tiers(interventions: list[dict[str, Any]]) -> dict[str, int]:
    tiers = {"quick_wins": 0, "medium": 0, "strategic": 0}
    for intervention in interventions:
        score = intervention["applicability_score"]
        if score <= 2:
            tiers["quick_wins"] += 1
        elif score <= 3:
            tiers["medium"] += 1
        else:
            tiers["strategic"] += 1
    return tiers


def analyze_records(
    records: list[dict[str, Any]],
    library: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Match interventions across measured records; return aggregated report."""
    library = library or load_library()
    record_results = [analyze_record(record, library=library) for record in records]
    aggregated = aggregate_interventions(record_results)
    return {
        "metadata": {
            "library_version": library.get("metadata", {}).get("version"),
            "record_count": len(record_results),
            "unique_interventions": len(aggregated),
        },
        "summary": {
            "label_breakdown": _label_breakdown(aggregated),
            "applicability_tiers": _applicability_tiers(aggregated),
            "top_priority": aggregated[:5],
        },
        "aggregated_interventions": aggregated,
        "records": record_results,
    }


def analyze_dataset(
    dataset: dict[str, Any],
    library: Optional[dict[str, Any]] = None,
    brand: Optional[str] = None,
) -> dict[str, Any]:
    library = library or load_library()
    records = dataset.get("records", [])
    if brand:
        records = [record for record in records if record.get("brand") == brand]

    record_results = [analyze_record(record, library=library) for record in records]
    aggregated = aggregate_interventions(record_results)

    brands = sorted({result.get("brand") for result in record_results if result.get("brand")})

    return {
        "metadata": {
            "library_version": library.get("metadata", {}).get("version"),
            "source_schema_version": dataset.get("metadata", {}).get("schema_version"),
            "brand_filter": brand,
            "record_count": len(record_results),
            "unique_interventions": len(aggregated),
        },
        "summary": {
            "brands": brands,
            "label_breakdown": _label_breakdown(aggregated),
            "applicability_tiers": _applicability_tiers(aggregated),
            "top_priority": aggregated[:5],
        },
        "aggregated_interventions": aggregated,
        "records": record_results,
    }


def print_report(report: dict[str, Any], source_label: str) -> None:
    metadata = report["metadata"]
    summary = report["summary"]

    print(f"\nIntervention Report — {source_label}")
    print(
        f"Records: {metadata['record_count']} | "
        f"Unique interventions: {metadata['unique_interventions']}"
    )

    if metadata.get("brand_filter"):
        print(f"Brand filter: {metadata['brand_filter']}")

    print("\nLabel breakdown:")
    for label, count in summary["label_breakdown"].items():
        print(f"  {label}: {count}")

    tiers = summary["applicability_tiers"]
    print(
        "\nApplicability tiers: "
        f"quick_wins={tiers['quick_wins']}, "
        f"medium={tiers['medium']}, "
        f"strategic={tiers['strategic']}"
    )

    print("\nTop interventions (by priority):")
    for intervention in report["aggregated_interventions"][:8]:
        print(
            f"  [{intervention['label']}] {intervention['title']} "
            f"(priority={intervention['priority_score']}, "
            f"applicability={intervention['applicability_score']}, "
            f"geo_impact={intervention['geo_impact_score']}, "
            f"triggers={intervention.get('trigger_count', 1)})"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate GEO interventions from audit records using the intervention library."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_DATASET,
        help="Measured dataset JSON (schema 3.0)",
    )
    parser.add_argument(
        "--library",
        type=Path,
        default=DEFAULT_LIBRARY,
        help="Intervention library JSON path",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Where to write the full interventions report JSON",
    )
    parser.add_argument(
        "--brand",
        type=str,
        default=None,
        help="Filter to a single brand",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Print summary only; do not write output file",
    )
    args = parser.parse_args()

    dataset = load_dataset(args.input)
    library = load_library(args.library)
    report = analyze_dataset(dataset, library=library, brand=args.brand)

    print_report(report, str(args.input))

    if not args.no_write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as file_handle:
            json.dump(report, file_handle, indent=2, ensure_ascii=False)
        print(f"\nFull report written to: {args.output}")


if __name__ == "__main__":
    main()
