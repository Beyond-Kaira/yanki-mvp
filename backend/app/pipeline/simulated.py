"""Simulated GEO audit: OpenRouter-only answer + structured signal extraction.

Ported from kaira-geo-api ``simulated.py`` SYSTEM_PROMPT path. No Tavily —
the model invents a realistic AI answer, then extracts GEO signals from it.

Conflicts resolved vs the Kaira original:
* ``sector`` is taken from KYC industry (not hardcoded ``fintech``)
* owned-domain checks use analysis URL domains (not ``BRAND_DOMAINS`` map)
* no Revolut/Monzo/etc. brand lists in this module

Remaining soft bias (not brand names): driver/gap *definitions* still mention
financial/product cues from the original prompt — they work for other sectors
but read fintech-flavoured.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Protocol

from app.providers.tavily import normalize_domain

SCHEMA_VERSION = "2.0"

DEFAULT_VISIBILITY_DRIVERS: dict[str, list[str]] = {
    "product_strength": [],
    "distribution_strength": [],
    "trust_strength": [],
    "brand_strength": [],
    "content_strength": [],
    "international_strength": [],
    "ux_strength": [],
}

DEFAULT_VISIBILITY_GAPS: dict[str, list[str]] = {
    "low_discoverability": [],
    "weak_ranking": [],
    "category_mismatch": [],
    "weak_trust_signals": [],
    "weak_feature_association": [],
    "competitor_dominance": [],
    "content_gap": [],
    "international_positioning_gap": [],
    "ux_positioning_gap": [],
    "reputation_gap": [],
}

DEFAULT_CITATION_METRICS = {
    "total_citations": 0,
    "target_brand_cited": False,
    "target_brand_citation_count": 0,
    "target_brand_citation_rank": 0,
    "owned_media_cited": False,
    "earned_media_cited": False,
    "competitor_citation_share": {},
}

# sector placeholder is filled per-call from KYC industry (avoids fintech lock-in).
SYSTEM_PROMPT_TEMPLATE = """
You are a GEO (Generative Engine Optimization) audit engine.

Your task is to evaluate AI search visibility for a target brand based on realistic AI-generated recommendations.

For each brand-query pair, perform two steps:

Step 1 — Simulate AI Answer
Generate the full answer exactly as a modern AI assistant (such as ChatGPT, Gemini, Perplexity, or Claude) would respond to the user query.

The simulated answer should reflect realistic recommendation behavior, including:
- ranking patterns
- competitor mentions
- recommendation reasoning
- trust cues
- product positioning
- realistic source citations as modern AI search interfaces provide (2-5 plausible sources with domain context)

Step 2 — Extract GEO Signals
Using the simulated answer as the ONLY source of truth, extract structured GEO audit signals for the target brand.

Important:
- Base all audit signals strictly on the simulated answer.
- Do not hallucinate signals that are not supported by the simulated answer.
- Evaluate visibility, ranking, positioning, trust, strengths, weaknesses, competitive dynamics, and citation patterns.
- The simulated answer must be generated independently of the target brand evaluation.
- Do not force inclusion of the target brand in the simulated answer.

Audit principle:
A missing brand mention is NOT absence of insight.
If the target brand is not surfaced, that itself is a strong GEO signal and must generate actionable audit insights explaining:
- why the brand was absent
- which competitors were surfaced instead
- what the brand could improve to increase visibility

Return ONLY valid JSON with this schema:

{{
  "brand": "string",
  "sector": "{sector}",
  "prompt": "string",
  "intent": "informational | comparison | transactional | alternative_search",
  "simulated_answer": "string",
  "mentioned": true,
  "rank_position": 1,
  "mention_context": "primary_recommendation | secondary_recommendation | comparison_candidate | alternative_option | competitor_only | not_mentioned",
  "competitors": ["string"],
  "answer_summary": "string",
  "recommendation_reasoning": "string",
  "citations": [
    {{
      "source_title": "string",
      "source_domain": "string",
      "source_type": "comparison | review | news | official | forum | regulatory | other",
      "url": "string",
      "brands_referenced": ["string"],
      "mentions_target_brand": true,
      "citation_position": 1
    }}
  ],
  "citation_metrics": {{
    "total_citations": 0,
    "target_brand_cited": false,
    "target_brand_citation_count": 0,
    "target_brand_citation_rank": 0,
    "owned_media_cited": false,
    "earned_media_cited": false,
    "competitor_citation_share": {{}}
  }},
  "visibility_drivers": {{
    "product_strength": ["string"],
    "distribution_strength": ["string"],
    "trust_strength": ["string"],
    "brand_strength": ["string"],
    "content_strength": ["string"],
    "international_strength": ["string"],
    "ux_strength": ["string"]
  }},
  "visibility_gaps": {{
    "low_discoverability": ["string"],
    "weak_ranking": ["string"],
    "category_mismatch": ["string"],
    "weak_trust_signals": ["string"],
    "weak_feature_association": ["string"],
    "competitor_dominance": ["string"],
    "content_gap": ["string"],
    "international_positioning_gap": ["string"],
    "ux_positioning_gap": ["string"],
    "reputation_gap": ["string"]
  }},
  "trust_signals": ["string"],
  "entities_associated_with_brand": ["string"],
  "sentiment": "positive | neutral | negative",
  "content_improvement_opportunities": ["string"]
}}

Mention context definitions:
- primary_recommendation: brand is the main recommendation.
- secondary_recommendation: brand is recommended but not top.
- comparison_candidate: brand appears in direct comparison.
- alternative_option: brand appears as an alternative.
- competitor_only: brand is only referenced as a competitor.
- not_mentioned: brand does not appear in the simulated answer.

Citation definitions:
- mentions_target_brand: true only if the target brand appears in source_title, source_domain, or brands_referenced for that citation.
- owned_media_cited: true if a citation referencing the target brand uses the brand's official domain.
- earned_media_cited: true if a citation referencing the target brand uses a third-party domain.
- target_brand_cited: true if at least one citation has mentions_target_brand true.
- mentioned and target_brand_cited are independent: a brand can be mentioned in prose without being cited, or cited without being the top recommendation.

Visibility driver category definitions:
- product_strength: product features, pricing, offerings, integrations, or tools.
- distribution_strength: availability, market presence, coverage, accessibility, or reach.
- trust_strength: regulation, safety, security, reputation, or institutional credibility.
- brand_strength: brand awareness, popularity, category leadership, or recognition.
- content_strength: comparison pages, guides, educational content, documentation, or explainers.
- international_strength: cross-border, multi-market, or global positioning strengths.
- ux_strength: app quality, onboarding, ease of use, digital experience, or interface quality.

Visibility gap category definitions:
- low_discoverability: brand is absent or rarely surfaced.
- weak_ranking: brand appears but ranks behind stronger competitors.
- category_mismatch: brand is weakly associated with prompt intent.
- weak_trust_signals: brand lacks strong trust, regulation, or safety signals.
- weak_feature_association: brand lacks strong association with key features.
- competitor_dominance: competitors dominate recommendation share.
- content_gap: brand lacks sufficient educational or comparison content.
- international_positioning_gap: brand is weak for global or cross-border positioning.
- ux_positioning_gap: brand is weakly associated with UX or digital experience.
- reputation_gap: brand lacks authority, popularity, or leadership positioning.

Rules:
- Use predefined keys exactly.
- Do not create additional keys.
- mentioned must be true only if the target brand appears in simulated_answer.
- rank_position must be 0 if mentioned is false.
- mention_context must be "not_mentioned" if mentioned is false.
- competitors must include brands appearing in simulated_answer.
- citations maximum 5 items.
- competitor_citation_share keys maximum 10 items.

If mentioned is false:
- all visibility_drivers categories must be empty arrays
- all trust_signals must be empty
- all entities_associated_with_brand must be empty
- visibility_gaps must contain at least one populated category
- content_improvement_opportunities must contain at least one actionable recommendation
- recommendation_reasoning must explicitly explain why the brand was not surfaced

If mentioned is true:
- visibility_gaps should still include weaknesses whenever relevant
- avoid returning fully empty visibility_gaps unless the brand has exceptionally strong positioning

If target_brand_cited is false:
- include at least one content_gap insight about missing citable third-party sources when citations exist
- if mentioned is true but target_brand_cited is false, explain that the brand appears without citation support

Length constraints:
- answer_summary maximum 2 sentences
- recommendation_reasoning maximum 2 sentences
- competitors maximum 10 items
- trust_signals maximum 5 items
- entities_associated_with_brand maximum 10 items
- content_improvement_opportunities maximum 5 items
- each visibility_drivers category maximum 3 items
- each visibility_gaps category maximum 3 items

Formatting:
- Do not use markdown
- Return complete valid JSON only
"""


class ChatLLM(Protocol):
    model: str

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = ...,
        max_tokens: int = ...,
        json_object: bool = ...,
    ) -> Any: ...


def build_system_prompt(sector: str = "") -> str:
    cleaned = (sector or "general").strip() or "general"
    return SYSTEM_PROMPT_TEMPLATE.format(sector=cleaned)


def parse_llm_json(content: str) -> tuple[dict[str, Any], str]:
    stripped = content.strip()
    if stripped.startswith("```json"):
        stripped = stripped.removeprefix("```json").strip()
    elif stripped.startswith("```"):
        stripped = stripped.removeprefix("```").strip()
    if stripped.endswith("```"):
        stripped = stripped.removesuffix("```").strip()

    try:
        return json.loads(stripped), "raw_json"
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if match:
        return json.loads(match.group()), "extracted_json"
    raise json.JSONDecodeError("Could not parse JSON", stripped, 0)


def _is_owned_domain(owned_domains: list[str], domain: str) -> bool:
    normalized = normalize_domain(domain)
    if not normalized:
        return False
    for owned in owned_domains:
        owned_norm = normalize_domain(owned)
        if not owned_norm:
            continue
        if normalized == owned_norm or normalized.endswith(f".{owned_norm}"):
            return True
    return False


def _citation_mentions_brand(citation: dict[str, Any], brand_lower: str) -> bool:
    if citation.get("mentions_target_brand"):
        return True
    title = (citation.get("source_title") or "").lower()
    domain = normalize_domain(citation.get("source_domain", ""))
    if brand_lower in title:
        return True
    if brand_lower.replace(" ", "") in domain.replace("-", ""):
        return True
    for referenced_brand in citation.get("brands_referenced", []):
        if referenced_brand.lower() == brand_lower:
            return True
    return False


def compute_citation_metrics(
    brand: str, citations: list[dict[str, Any]], *, owned_domains: list[str]
) -> dict[str, Any]:
    brand_lower = brand.lower()
    citations = citations or []
    target_citations = [
        citation for citation in citations if _citation_mentions_brand(citation, brand_lower)
    ]
    owned_media_cited = any(
        _is_owned_domain(owned_domains, citation.get("source_domain", ""))
        for citation in target_citations
    )
    earned_media_cited = any(
        not _is_owned_domain(owned_domains, citation.get("source_domain", ""))
        for citation in target_citations
    )
    competitor_citation_share: dict[str, int] = {}
    for citation in citations:
        for referenced_brand in citation.get("brands_referenced", []):
            if referenced_brand.lower() == brand_lower:
                continue
            competitor_citation_share[referenced_brand] = (
                competitor_citation_share.get(referenced_brand, 0) + 1
            )
    citation_positions = [
        citation.get("citation_position", 0)
        for citation in target_citations
        if citation.get("citation_position", 0) > 0
    ]
    return {
        "total_citations": len(citations),
        "target_brand_cited": len(target_citations) > 0,
        "target_brand_citation_count": len(target_citations),
        "target_brand_citation_rank": min(citation_positions) if citation_positions else 0,
        "owned_media_cited": owned_media_cited,
        "earned_media_cited": earned_media_cited,
        "competitor_citation_share": competitor_citation_share,
    }


def _append_unique(items: list[str], message: str) -> None:
    if message and message not in items:
        items.append(message)


def _ensure_map(source: dict | None, defaults: dict) -> dict:
    merged = deepcopy(defaults)
    if source:
        for key in merged:
            merged[key] = list(source.get(key) or [])
    return merged


def normalize_record(
    record: dict[str, Any], *, owned_domains: list[str], sector: str = ""
) -> dict[str, Any]:
    record["visibility_drivers"] = _ensure_map(
        record.get("visibility_drivers"), DEFAULT_VISIBILITY_DRIVERS
    )
    record["visibility_gaps"] = _ensure_map(record.get("visibility_gaps"), DEFAULT_VISIBILITY_GAPS)
    record.setdefault("trust_signals", [])
    record.setdefault("entities_associated_with_brand", [])
    record.setdefault("competitors", [])
    record.setdefault("content_improvement_opportunities", [])
    record.setdefault("recommendation_reasoning", "")
    record.setdefault("citations", [])
    record.setdefault("citation_metrics", deepcopy(DEFAULT_CITATION_METRICS))
    if sector:
        record["sector"] = sector

    brand = record.get("brand", "")
    brand_lower = brand.lower()
    citations = []
    for index, citation in enumerate((record.get("citations") or [])[:5], start=1):
        citations.append(
            {
                "source_title": citation.get("source_title", ""),
                "source_domain": citation.get("source_domain", ""),
                "source_type": citation.get("source_type", "other"),
                "url": citation.get("url", ""),
                "brands_referenced": citation.get("brands_referenced", []),
                "mentions_target_brand": _citation_mentions_brand(citation, brand_lower),
                "citation_position": citation.get("citation_position") or index,
            }
        )
    record["citations"] = citations
    record["citation_metrics"] = compute_citation_metrics(
        brand, citations, owned_domains=owned_domains
    )

    simulated_answer = (record.get("simulated_answer") or "").lower()
    brand_is_present = bool(brand_lower) and brand_lower in simulated_answer
    # Also honour aliases-style substring already covered by brand name only here;
    # aliases are enforced by the caller embedding them in the user message.

    if not brand_is_present:
        record["mentioned"] = False
        record["rank_position"] = 0
        record["mention_context"] = "not_mentioned"
        for key in record["visibility_drivers"]:
            record["visibility_drivers"][key] = []
        record["trust_signals"] = []
        record["entities_associated_with_brand"] = []
        competitors = record.get("competitors") or []
        record["recommendation_reasoning"] = (
            f"{brand} was not surfaced in the simulated answer, while competitors "
            f"such as {', '.join(competitors) or 'other brands'} were mentioned."
        )
        _append_unique(
            record["visibility_gaps"]["low_discoverability"],
            f"{brand} was not mentioned in the simulated answer.",
        )
        if competitors:
            _append_unique(
                record["visibility_gaps"]["competitor_dominance"],
                "Simulated answer favored: " + ", ".join(competitors[:5]) + ".",
            )
        _append_unique(
            record["content_improvement_opportunities"],
            f"Publish comparison and category content so AI assistants can cite {brand}.",
        )
    else:
        record["mentioned"] = True
        if not record.get("mention_context") or record["mention_context"] == "not_mentioned":
            record["mention_context"] = "secondary_recommendation"

    if record["mentioned"] and not record["citation_metrics"].get("target_brand_cited"):
        _append_unique(
            record["visibility_gaps"]["content_gap"],
            f"{brand} appears in the answer without citation support.",
        )

    record["grounded_answer"] = record.get("simulated_answer") or ""
    record["measurement_mode"] = "simulated"
    record["search_provider"] = None
    record["search_results"] = []
    record["search_visibility"] = {}
    record["owned_domains"] = owned_domains
    record["schema_version"] = SCHEMA_VERSION
    record["generated_at"] = datetime.now(UTC).isoformat()
    record["error"] = False
    return record


def mock_simulated_record(
    *,
    brand: str,
    prompt: str,
    prompt_group: str,
    owned_domains: list[str],
    sector: str = "",
    aliases: list[str] | None = None,
) -> dict[str, Any]:
    """Deterministic DRY_RUN simulated record (no LLM)."""
    mentioned = True  # mock always surfaces the brand for a non-zero demo score
    answer = (
        f"{brand} is a strong option for this query. Other names that often appear "
        f"include Acme and Globex. Sources typically cite review sites and {brand}'s site."
    )
    record = {
        "brand": brand,
        "sector": sector or "general",
        "prompt": prompt,
        "prompt_group": prompt_group,
        "intent": "informational",
        "simulated_answer": answer,
        "mentioned": mentioned,
        "rank_position": 1,
        "mention_context": "primary_recommendation",
        "competitors": ["Acme", "Globex"],
        "answer_summary": f"Mock simulated answer recommending {brand}.",
        "recommendation_reasoning": f"{brand} is presented as a primary option.",
        "citations": [
            {
                "source_title": f"{brand} overview",
                "source_domain": owned_domains[0] if owned_domains else "example.com",
                "source_type": "official",
                "url": f"https://{(owned_domains[0] if owned_domains else 'example.com')}/",
                "brands_referenced": [brand],
                "mentions_target_brand": True,
                "citation_position": 1,
            },
            {
                "source_title": "Category roundup",
                "source_domain": "reviews.example",
                "source_type": "comparison",
                "url": "https://reviews.example/roundup",
                "brands_referenced": ["Acme", "Globex", brand],
                "mentions_target_brand": True,
                "citation_position": 2,
            },
        ],
        "visibility_drivers": {
            **deepcopy(DEFAULT_VISIBILITY_DRIVERS),
            "brand_strength": [f"{brand} is named as a primary recommendation."],
        },
        "visibility_gaps": deepcopy(DEFAULT_VISIBILITY_GAPS),
        "trust_signals": [],
        "entities_associated_with_brand": aliases or [],
        "sentiment": "positive",
        "content_improvement_opportunities": [],
        "model": "mock",
    }
    return normalize_record(record, owned_domains=owned_domains, sector=sector)


def run_simulated_audit(
    *,
    brand: str,
    prompt: str,
    prompt_group: str,
    owned_domains: list[str],
    aliases: list[str] | None = None,
    sector: str = "",
    llm: ChatLLM | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run one simulated audit for ``(brand, prompt)`` via OpenRouter (or mock)."""
    if dry_run or llm is None:
        return mock_simulated_record(
            brand=brand,
            prompt=prompt,
            prompt_group=prompt_group,
            owned_domains=owned_domains,
            sector=sector,
            aliases=aliases,
        )

    alias_line = ", ".join(aliases or []) or "(none)"
    user_content = (
        f"Brand: {brand}\n"
        f"Aliases: {alias_line}\n"
        f"Owned domains: {', '.join(owned_domains) or '(unknown)'}\n"
        f"Sector: {sector or 'general'}\n"
        f"Prompt Group: {prompt_group}\n"
        f"Prompt: {prompt}"
    )
    try:
        result = llm.chat(
            [
                {"role": "system", "content": build_system_prompt(sector)},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            max_tokens=4500,
            json_object=True,
        )
        parsed, response_format = parse_llm_json(result.text)
        parsed = normalize_record(parsed, owned_domains=owned_domains, sector=sector)
        parsed["brand"] = brand
        parsed["prompt"] = prompt
        parsed["prompt_group"] = prompt_group
        parsed["model"] = getattr(llm, "model", "")
        parsed["response_format"] = response_format
        return parsed
    except Exception as exc:  # noqa: BLE001
        return {
            "brand": brand,
            "prompt": prompt,
            "prompt_group": prompt_group,
            "model": getattr(llm, "model", ""),
            "error": True,
            "error_stage": "simulated_audit",
            "error_response": str(exc),
            "simulated_answer": "",
            "grounded_answer": "",
            "mentioned": False,
            "mention_context": "not_mentioned",
            "citation_metrics": deepcopy(DEFAULT_CITATION_METRICS),
            "sentiment": "neutral",
            "measurement_mode": "simulated",
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "owned_domains": owned_domains,
        }
