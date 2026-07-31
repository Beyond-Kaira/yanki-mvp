"""
Audit reliability of LLM-extracted GEO fields against measured evidence.

Pipeline (run top to bottom via main()):
    1. load_dataset()        — read measured JSON (Tavily search + citations)
    2. analyze_dataset()       — loop every record
    3. analyze_record()        — per record: build evidence, audit each claim
    4. build_evidence_corpus() — merge search/citations/answer into ground truth
    5. audit_gap_claim()       — check each visibility_gaps sentence
    6. audit_driver_claim()    — check each visibility_drivers sentence
    7. audit_entity()          — check each entities_associated_with_brand item
    8. _score_audits()         — turn statuses into 0–1 reliability_score
    9. print_report()          — terminal summary + write reliability_report.json

Ground truth = measured fields only (not the LLM gap/driver text being tested):
    search_results, citations, grounded_answer, search_visibility, citation_metrics

Default input:  datas/geo_fintech_measured_dataset_all_v1.json
Default output: datas/reliability_report.json
"""

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_DATASET = None  # unused in Yanki (in-memory records)
DEFAULT_OUTPUT = None

# Competitor names for entity misclassification checks come from the record
# itself (KYC competitors), not a hardcoded fintech list.
KNOWN_BRANDS: set[str] = set()

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

DRIVER_CATEGORIES = [
    "product_strength",
    "distribution_strength",
    "trust_strength",
    "brand_strength",
    "content_strength",
    "international_strength",
    "ux_strength",
]

# Maps audit status to numeric score for reliability_score averaging.
STATUS_SCORES = {
    "verified": 1.0,  # claim matches measured data exactly
    "partial": 0.5,  # plausible but not fully provable
    "unverified": 0.25,  # no evidence found
    "contradicted": 0.0,  # claim conflicts with measured data
    "not_applicable": None,
}


@dataclass
class ClaimAudit:
    """Result of checking one gap, driver, or entity against measured evidence.

    Attributes:
        field_type: Which JSON field was audited (e.g. visibility_gaps).
        category: Sub-category key (e.g. weak_ranking) or "entity".
        claim: The exact string from the dataset being evaluated.
        status: verified | partial | unverified | contradicted.
        reason: Human-readable explanation of the verdict.
        evidence_refs: Which ground-truth fields supported the decision.
    """

    field_type: str
    category: str
    claim: str
    status: str
    reason: str
    evidence_refs: list[str] = field(default_factory=list)


def load_dataset(path: Path) -> dict:
    """Step 1 — Load the measured dataset JSON from disk.

    Args:
        path: Path to geo_fintech_measured_dataset_*.json (schema 3.0).

    Returns:
        Parsed dataset dict with metadata, prompt_groups, and records.
    """
    with open(path, encoding="utf-8") as file_handle:
        return json.load(file_handle)


def build_evidence_corpus(record: dict) -> dict[str, Any]:
    """Step 2 — Build the ground-truth evidence bundle for one record.

    Merges all measured (non-LLM-interpreted) sources into searchable text
    and keeps structured metrics for deterministic checks.

    Args:
        record: Single item from dataset records[].

    Returns:
        Dict with:
            - search_text / citation_text / answer_text / full_text (lowercased)
            - search_visibility, citation_metrics, mentioned (structured facts)
            - raw search_results and citations lists for reference
    """
    brand = record.get("brand", "")
    search_texts = []
    citation_texts = []
    urls = []

    for result in record.get("search_results", []):
        block = " ".join(
            [
                result.get("title", ""),
                result.get("snippet", ""),
                result.get("domain", ""),
                " ".join(result.get("brands_mentioned", [])),
            ]
        )
        search_texts.append(block)
        urls.append(result.get("url", ""))

    for citation in record.get("citations", []):
        block = " ".join(
            [
                citation.get("source_title", ""),
                citation.get("source_domain", ""),
                citation.get("url", ""),
                " ".join(citation.get("brands_referenced", [])),
            ]
        )
        citation_texts.append(block)
        urls.append(citation.get("url", ""))

    grounded_answer = record.get("grounded_answer") or record.get("simulated_answer", "")

    return {
        "brand": brand,
        "brand_lower": brand.lower(),
        "search_text": " ".join(search_texts).lower(),
        "citation_text": " ".join(citation_texts).lower(),
        "answer_text": grounded_answer.lower(),
        "full_text": " ".join(search_texts + citation_texts + [grounded_answer]).lower(),
        "urls": [url for url in urls if url],
        "search_visibility": record.get("search_visibility", {}),
        "citation_metrics": record.get("citation_metrics", {}),
        "mentioned": bool(record.get("mentioned")),
        "search_results": record.get("search_results", []),
        "citations": record.get("citations", []),
    }


def _claim_mentions_brand_absent(claim: str, brand_lower: str) -> bool:
    """Return True if the claim text implies the target brand is missing.

    Used to detect contradictions: e.g. claim says "not in results" but
    search_visibility.brand_in_results is True.
    """
    patterns = [
        (
            rf"{re.escape(brand_lower)} (?:is |was )?not "
            rf"(?:present|mentioned|surfaced|included|cited|in)"
        ),
        rf"{re.escape(brand_lower)} did not appear",
        rf"{re.escape(brand_lower)} (?:has no|lacks) visibility",
        rf"no owned-domain result.*{re.escape(brand_lower)}",
    ]
    claim_lower = claim.lower()
    return any(re.search(pattern, claim_lower) for pattern in patterns)


def _claim_mentions_brand_present(claim: str, brand_lower: str) -> bool:
    """Return True if the claim text implies the target brand is visible.

    Used to detect contradictions when brand is actually absent from search/answer.
    """
    patterns = [
        rf"{re.escape(brand_lower)} (?:is |was )?mentioned",
        rf"{re.escape(brand_lower)} appears",
        rf"{re.escape(brand_lower)} (?:ranks|rank)",
        rf"{re.escape(brand_lower)} (?:has|have) (?:a |some )?presence",
    ]
    claim_lower = claim.lower()
    return any(re.search(pattern, claim_lower) for pattern in patterns)


def _extract_rank_from_claim(claim: str) -> int | None:
    """Parse a numeric rank from free-text gap claims.

    Examples matched: "ranks 3rd", "ranking 2", "2nd in search results".

    Returns:
        Integer rank if found, else None.
    """
    match = re.search(r"rank(?:s|ing)?\s+(\d+)(?:st|nd|rd|th)?", claim.lower())
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)(?:st|nd|rd|th)\s+(?:in|among)", claim.lower())
    if match:
        return int(match.group(1))
    return None


def _is_deterministic_system_gap(claim: str) -> bool:
    """Return True for gap lines auto-injected by measured pipeline (always reliable).

    These are not LLM-generated — they come from measured search_visibility
      in merge_measured_record().
    """
    return claim.startswith("Search results favored:") or claim.startswith("No owned-domain result")


def audit_gap_claim(claim: str, category: str, evidence: dict) -> ClaimAudit:
    """Step 3a — Audit one visibility_gaps claim against measured evidence.

    Decision order (first match wins):
        1. System-injected lines (owned-domain, competitor share) → verified
        2. Exact phrase rules (not in search, not cited, not in answer) → verified/contradicted
        3. Rank claims → compare to search_visibility.brand_best_rank
        4. Absence/presence contradiction checks
        5. Competitor dominance qualitative → partial
        6. Token overlap with evidence corpus → partial
        7. Fallback → unverified

    Args:
        claim: One string from visibility_gaps[category].
        category: Gap category key (e.g. content_gap).
        evidence: Output of build_evidence_corpus().

    Returns:
        ClaimAudit with status and reason.
    """
    brand_lower = evidence["brand_lower"]
    visibility = evidence["search_visibility"]
    metrics = evidence["citation_metrics"]
    refs: list[str] = []

    if _is_deterministic_system_gap(claim):
        if claim.startswith("No owned-domain result"):
            ok = not visibility.get("owned_domain_in_results", False)
            return ClaimAudit(
                "visibility_gaps",
                category,
                claim,
                "verified" if ok else "contradicted",
                "Matches search_visibility.owned_domain_in_results.",
                ["search_visibility.owned_domain_in_results"],
            )
        return ClaimAudit(
            "visibility_gaps",
            category,
            claim,
            "verified",
            "Deterministic competitor share line from measured search.",
            ["search_visibility.competitor_result_share"],
        )

    if "did not appear in the top" in claim.lower() and "search results" in claim.lower():
        ok = not visibility.get("brand_in_results", False)
        return ClaimAudit(
            "visibility_gaps",
            category,
            claim,
            "verified" if ok else "contradicted",
            f"brand_in_results={visibility.get('brand_in_results')}.",
            ["search_visibility.brand_in_results"],
        )

    if "not mentioned in the grounded answer" in claim.lower():
        ok = not evidence["mentioned"]
        return ClaimAudit(
            "visibility_gaps",
            category,
            claim,
            "verified" if ok else "contradicted",
            f"mentioned={evidence['mentioned']}.",
            ["grounded_answer.mentioned"],
        )

    if "not present in search results" in claim.lower():
        ok = not visibility.get("brand_in_results", False)
        return ClaimAudit(
            "visibility_gaps",
            category,
            claim,
            "verified" if ok else "contradicted",
            f"brand_in_results={visibility.get('brand_in_results')}.",
            ["search_visibility.brand_in_results"],
        )

    if "was not cited" in claim.lower() or "not cited in any" in claim.lower():
        ok = not metrics.get("target_brand_cited", False)
        return ClaimAudit(
            "visibility_gaps",
            category,
            claim,
            "verified" if ok else "contradicted",
            f"target_brand_cited={metrics.get('target_brand_cited')}.",
            ["citation_metrics.target_brand_cited"],
        )

    claimed_rank = _extract_rank_from_claim(claim)
    if claimed_rank is not None and "rank" in claim.lower():
        actual_rank = visibility.get("brand_best_rank", 0)
        if not visibility.get("brand_in_results"):
            return ClaimAudit(
                "visibility_gaps",
                category,
                claim,
                "contradicted",
                f"Claim cites rank {claimed_rank} but brand not in search results.",
                ["search_visibility.brand_best_rank"],
            )
        if actual_rank == claimed_rank:
            return ClaimAudit(
                "visibility_gaps",
                category,
                claim,
                "verified",
                f"Matches search_visibility.brand_best_rank={actual_rank}.",
                ["search_visibility.brand_best_rank"],
            )
        return ClaimAudit(
            "visibility_gaps",
            category,
            claim,
            "contradicted",
            f"Claim rank {claimed_rank} != measured brand_best_rank {actual_rank}.",
            ["search_visibility.brand_best_rank"],
        )

    if _claim_mentions_brand_absent(claim, brand_lower):
        if visibility.get("brand_in_results") or evidence["mentioned"]:
            return ClaimAudit(
                "visibility_gaps",
                category,
                claim,
                "contradicted",
                "Claim implies absence but brand appears in search and/or answer.",
                ["search_visibility.brand_in_results", "grounded_answer.mentioned"],
            )

    if _claim_mentions_brand_present(claim, brand_lower):
        if not visibility.get("brand_in_results") and not evidence["mentioned"]:
            return ClaimAudit(
                "visibility_gaps",
                category,
                claim,
                "contradicted",
                "Claim implies presence but brand absent from search and answer.",
                ["search_visibility.brand_in_results", "grounded_answer.mentioned"],
            )

    if category == "competitor_dominance":
        competitors = visibility.get("competitor_result_share", {})
        if competitors:
            top_name = max(competitors, key=competitors.get)
            if top_name.lower() in claim.lower():
                refs.append("search_visibility.competitor_result_share")
                return ClaimAudit(
                    "visibility_gaps",
                    category,
                    claim,
                    "partial",
                    f"Top competitor {top_name} referenced; qualitative dominance claim.",
                    refs,
                )

    overlap = _text_overlap_score(claim, evidence["full_text"])
    if overlap >= 0.35:
        return ClaimAudit(
            "visibility_gaps",
            category,
            claim,
            "partial",
            f"Qualitative claim with evidence term overlap ({overlap:.0%}).",
            ["search_results", "citations", "grounded_answer"],
        )

    return ClaimAudit(
        "visibility_gaps",
        category,
        claim,
        "unverified",
        "No deterministic rule matched; insufficient evidence overlap.",
        [],
    )


def audit_driver_claim(claim: str, category: str, evidence: dict) -> ClaimAudit:
    """Step 3b — Audit one visibility_drivers claim against measured evidence.

    Drivers should only exist when the brand is mentioned in the grounded answer.
    A valid driver must name the brand and overlap with the evidence corpus.

    Args:
        claim: One string from visibility_drivers[category].
        category: Driver category key (e.g. product_strength).
        evidence: Output of build_evidence_corpus().

    Returns:
        ClaimAudit with status and reason.
    """
    brand_lower = evidence["brand_lower"]

    if not evidence["mentioned"]:
        return ClaimAudit(
            "visibility_drivers",
            category,
            claim,
            "contradicted",
            "Drivers should be empty when brand is not mentioned in grounded answer.",
            ["grounded_answer.mentioned"],
        )

    if brand_lower not in claim.lower():
        return ClaimAudit(
            "visibility_drivers",
            category,
            claim,
            "partial",
            "Driver claim does not explicitly name the target brand.",
            ["grounded_answer"],
        )

    overlap = _text_overlap_score(claim, evidence["full_text"])
    if overlap >= 0.3:
        return ClaimAudit(
            "visibility_drivers",
            category,
            claim,
            "verified" if overlap >= 0.45 else "partial",
            f"Brand-specific driver with evidence overlap ({overlap:.0%}).",
            ["search_results", "citations", "grounded_answer"],
        )

    return ClaimAudit(
        "visibility_drivers",
        category,
        claim,
        "unverified",
        "Brand named but claim not supported by measured evidence text.",
        [],
    )


def audit_entity(entity: str, evidence: dict) -> ClaimAudit:
    """Step 3c — Audit one entities_associated_with_brand entry.

    This field should list concepts/products tied to the target brand — NOT
    competitor bank names (those belong in competitors[]).

    Rules:
        - Target brand itself → partial (redundant)
        - Known competitor brand → contradicted (misclassified)
        - Other term found in evidence → verified
        - Not in evidence → unverified

    Args:
        entity: One string from entities_associated_with_brand[].
        evidence: Output of build_evidence_corpus().

    Returns:
        ClaimAudit with status and reason.
    """
    brand_lower = evidence["brand_lower"]
    entity_lower = entity.lower()

    if entity_lower == brand_lower:
        return ClaimAudit(
            "entities_associated_with_brand",
            "entity",
            entity,
            "partial",
            "Target brand listed as its own associated entity (redundant).",
            ["grounded_answer"],
        )

    if entity_lower in evidence.get("competitor_names", set()) or (
        entity_lower in KNOWN_BRANDS and entity_lower != brand_lower
    ):
        return ClaimAudit(
            "entities_associated_with_brand",
            "entity",
            entity,
            "contradicted",
            "Competitor brand in entities_associated_with_brand — "
            "should be competitors field, not brand entities.",
            ["citations", "grounded_answer"],
        )

    overlap = _text_overlap_score(entity, evidence["full_text"])
    if overlap >= 0.5 or entity_lower in evidence["full_text"]:
        return ClaimAudit(
            "entities_associated_with_brand",
            "entity",
            entity,
            "verified",
            "Non-brand entity term appears in measured evidence.",
            ["search_results", "citations", "grounded_answer"],
        )

    return ClaimAudit(
        "entities_associated_with_brand",
        "entity",
        entity,
        "unverified",
        "Entity not found in measured evidence corpus.",
        [],
    )


def _text_overlap_score(claim: str, corpus: str) -> float:
    """Fallback similarity: fraction of meaningful claim tokens found in corpus.

    Used when no deterministic rule applies. Strips short words and stopwords.
    Higher score → claim vocabulary appears in Tavily/citation/answer text.

    Returns:
        Float 0.0–1.0 (ratio of matched tokens).
    """
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", claim.lower())
        if len(token) > 3
        and token not in {"monzo", "that", "with", "from", "this", "have", "been", "were", "their"}
    }
    if not tokens:
        return 0.0
    hits = sum(1 for token in tokens if token in corpus)
    return hits / len(tokens)


def _score_audits(audits: list[ClaimAudit]) -> dict:
    """Step 4 — Aggregate claim audits into counts and a single reliability_score.

    reliability_score = average of STATUS_SCORES per audit (0–1).
    Returns null score when there are zero audits (e.g. empty drivers).

    Args:
        audits: List of ClaimAudit from one field type.

    Returns:
        Dict with total, verified/partial/unverified/contradicted counts, reliability_score.
    """
    if not audits:
        return {
            "total": 0,
            "verified": 0,
            "partial": 0,
            "unverified": 0,
            "contradicted": 0,
            "reliability_score": None,
        }

    counts = {status: 0 for status in STATUS_SCORES if status != "not_applicable"}
    for audit in audits:
        counts[audit.status] = counts.get(audit.status, 0) + 1

    scores: list[float] = [
        score
        for audit in audits
        if (score := STATUS_SCORES[audit.status]) is not None
    ]
    return {
        "total": len(audits),
        **counts,
        "reliability_score": round(sum(scores) / len(scores), 3) if scores else None,
    }


def analyze_record(record: dict) -> dict:
    """Step 5 — Run full reliability audit on one dataset record.

    Flow:
        1. Skip if record.error
        2. build_evidence_corpus()
        3. Loop all gap/driver/entity items → audit functions
        4. _score_audits() per field type
        5. Compute overall_reliability_score across all audits

    Args:
        record: Single measured dataset record (schema 3.0).

    Returns:
        Report dict with summary, gap_audits, driver_audits, entity_audits.
    """
    if record.get("error"):
        return {
            "brand": record.get("brand"),
            "prompt": record.get("prompt"),
            "skipped": True,
            "reason": "error record",
        }

    competitors = {str(name).lower() for name in (record.get("competitors") or []) if name}
    evidence = build_evidence_corpus(record)
    evidence["competitor_names"] = competitors
    gap_audits: list[ClaimAudit] = []
    driver_audits: list[ClaimAudit] = []
    entity_audits: list[ClaimAudit] = []

    for category in GAP_CATEGORIES:
        for claim in record.get("visibility_gaps", {}).get(category, []) or []:
            gap_audits.append(audit_gap_claim(claim, category, evidence))

    for category in DRIVER_CATEGORIES:
        for claim in record.get("visibility_drivers", {}).get(category, []) or []:
            driver_audits.append(audit_driver_claim(claim, category, evidence))

    for entity in record.get("entities_associated_with_brand", []) or []:
        entity_audits.append(audit_entity(entity, evidence))

    gap_summary = _score_audits(gap_audits)
    driver_summary = _score_audits(driver_audits)
    entity_summary = _score_audits(entity_audits)

    all_audits = gap_audits + driver_audits + entity_audits
    overall_scores: list[float] = [
        score
        for audit in all_audits
        if (score := STATUS_SCORES[audit.status]) is not None
    ]
    overall_score = (
        round(sum(overall_scores) / len(overall_scores), 3) if overall_scores else None
    )

    return {
        "brand": record.get("brand"),
        "prompt": record.get("prompt"),
        "prompt_group": record.get("prompt_group"),
        "measurement_mode": record.get("measurement_mode"),
        "mentioned": record.get("mentioned"),
        "citation_count": len(record.get("citations", [])),
        "target_brand_cited": record.get("citation_metrics", {}).get("target_brand_cited"),
        "summary": {
            "visibility_gaps": gap_summary,
            "visibility_drivers": driver_summary,
            "entities_associated_with_brand": entity_summary,
            "overall_reliability_score": overall_score,
        },
        "gap_audits": [audit.__dict__ for audit in gap_audits],
        "driver_audits": [audit.__dict__ for audit in driver_audits],
        "entity_audits": [audit.__dict__ for audit in entity_audits],
    }


def analyze_records(records: list[dict]) -> dict:
    """Analyze a list of measured records in memory; return mean reliability."""
    analyses = [analyze_record(record) for record in records]
    active = [item for item in analyses if not item.get("skipped")]
    overall_scores = [
        item["summary"]["overall_reliability_score"]
        for item in active
        if item["summary"].get("overall_reliability_score") is not None
    ]
    mean = round(sum(overall_scores) / len(overall_scores), 3) if overall_scores else None
    return {
        "reliability_score": mean,
        "record_count": len(analyses),
        "active_count": len(active),
        "records": analyses,
    }


def analyze_dataset(dataset_path: Path) -> dict:
    """Step 6 — Analyze every record and compute dataset-level aggregates.

    Args:
        dataset_path: Path to measured dataset JSON.

    Returns:
        Full report dict with metadata, aggregate scores, and records[].
    """
    dataset = load_dataset(dataset_path)
    records = dataset.get("records", [])
    analyses = [analyze_record(record) for record in records]
    active = [item for item in analyses if not item.get("skipped")]

    def avg_score(key: str) -> float | None:
        """Average reliability_score for one summary field across all records."""
        scores = [
            item["summary"][key]["reliability_score"]
            for item in active
            if item["summary"][key]["reliability_score"] is not None
        ]
        return round(sum(scores) / len(scores), 3) if scores else None

    overall_scores = [
        item["summary"]["overall_reliability_score"]
        for item in active
        if item["summary"]["overall_reliability_score"] is not None
    ]

    return {
        "metadata": {
            "source_dataset": str(dataset_path),
            "schema_version": dataset.get("metadata", {}).get("schema_version"),
            "record_count": len(records),
            "analyzed_count": len(active),
            "generated_at": dataset.get("metadata", {}).get("last_updated_at"),
        },
        "aggregate": {
            "visibility_gaps_reliability": avg_score("visibility_gaps"),
            "visibility_drivers_reliability": avg_score("visibility_drivers"),
            "entities_reliability": avg_score("entities_associated_with_brand"),
            "overall_reliability_score": (
                round(sum(overall_scores) / len(overall_scores), 3) if overall_scores else None
            ),
        },
        "records": analyses,
    }


def print_report(report: dict) -> None:
    """Step 7 — Print human-readable summary to terminal.

    Shows aggregate scores, per-record breakdown, and flags contradicted/
    unverified items. Full detail is in the JSON file.

    Args:
        report: Output of analyze_dataset().
    """
    meta = report["metadata"]
    agg = report["aggregate"]

    print(f"\nReliability Report — {meta['source_dataset']}")
    print(f"Schema {meta.get('schema_version')} | {meta['analyzed_count']} records\n")
    print("Aggregate scores (0–1):")
    print(f"  visibility_gaps:                  {agg['visibility_gaps_reliability']}")
    print(f"  visibility_drivers:               {agg['visibility_drivers_reliability']}")
    print(f"  entities_associated_with_brand:   {agg['entities_reliability']}")
    print(f"  overall:                          {agg['overall_reliability_score']}\n")

    for item in report["records"]:
        if item.get("skipped"):
            continue
        summary = item["summary"]
        print(f"— {item['brand']} | {item['prompt'][:55]}...")
        print(
            f"  gaps {summary['visibility_gaps']['reliability_score']} "
            f"({summary['visibility_gaps']['verified']}v/"
            f"{summary['visibility_gaps']['partial']}p/"
            f"{summary['visibility_gaps']['unverified']}u/"
            f"{summary['visibility_gaps']['contradicted']}c)"
        )
        print(
            f"  drivers {summary['visibility_drivers']['reliability_score']} "
            f"| entities {summary['entities_associated_with_brand']['reliability_score']}"
        )

        for audit in item["entity_audits"]:
            if audit["status"] in {"contradicted", "unverified"}:
                print(f"    ! entity [{audit['status']}]: {audit['claim']} — {audit['reason']}")

        for audit in item["gap_audits"]:
            if audit["status"] == "contradicted":
                print(
                    f"    ! gap [{audit['category']}]: {audit['claim'][:70]}... — {audit['reason']}"
                )


def main():
    """CLI entrypoint: parse args → analyze → print → write JSON report.

    Usage:
        python reliability_analyzer.py
        python reliability_analyzer.py --input datas/foo.json --output datas/bar.json
        python reliability_analyzer.py --no-write
    """
    parser = argparse.ArgumentParser(
        description=(
            "Audit reliability of visibility_gaps, visibility_drivers, "
            "and entities against measured citations."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_DATASET,
        help="Measured dataset JSON (default: geo_fintech_measured_dataset_all_v1.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Where to write full JSON report",
    )
    parser.add_argument(
        "--no-write", action="store_true", help="Print summary only, do not write JSON"
    )
    args = parser.parse_args()

    if not args.input.exists():
        fallback = Path("datas/geo_fintech_measured_dataset_all.json")
        if fallback.exists():
            args.input = fallback
        else:
            raise FileNotFoundError(f"Dataset not found: {args.input}")

    report = analyze_dataset(args.input)
    print_report(report)

    if not args.no_write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as file_handle:
            json.dump(report, file_handle, indent=2, ensure_ascii=False)
        print(f"\nFull report written to: {args.output}")


if __name__ == "__main__":
    main()
