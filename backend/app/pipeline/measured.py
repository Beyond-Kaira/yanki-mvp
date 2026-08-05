"""Measured GEO audit: Tavily search → visibility → grounded answer → audit.

Ported from kaira-geo-api ``measured.py``, adapted for Yanki:

* owned domains + competitors come from KYC / analysis URL (not fintech hardcodes)
* LLM calls go through :class:`OpenRouterProvider` (or mock under DRY_RUN)
* search goes through :class:`TavilyClient` (or ``mock_search`` under DRY_RUN)
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Protocol

from app.providers.tavily import mock_search, normalize_domain

SCHEMA_VERSION = "3.0"

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

GROUNDED_ANSWER_SYSTEM_PROMPT = """
You are a grounded AI search assistant.

You will receive a user query and numbered search results from a web search API.
Write an answer using ONLY the provided search results.

Rules:
- Cite sources inline as [1], [2], etc. matching result rank numbers.
- Do not invent brands, facts, or URLs not supported by the results.
- Do not assume knowledge outside the provided results.
- Return ONLY valid JSON:

{
  "grounded_answer": "string",
  "citations": [
    {
      "result_rank": 1,
      "source_title": "string",
      "source_domain": "string",
      "url": "string",
      "source_type": "comparison | review | news | official | forum | regulatory | other",
      "brands_referenced": ["string"],
      "citation_position": 1
    }
  ],
  "competitors": ["string"],
  "answer_summary": "string"
}

- citations must reference only result ranks present in the input.
- competitors lists brands mentioned in grounded_answer.
- maximum 5 citations.
"""

AUDIT_EXTRACTION_SYSTEM_PROMPT = (
    "\n"
    "You are a GEO audit analyst.\n"
    "\n"
    "You receive measured visibility data from a real web search pass and a grounded answer.\n"
    "Your job is to audit ONE target brand using ONLY the provided evidence.\n"
    "\n"
    "Rules:\n"
    "- Every visibility_gaps item must be a string insight derived from evidence.\n"
    "- recommendation_reasoning must cite whether absence is in search results, grounded "
    "answer, or both.\n"
    "- visibility_drivers must be empty if the brand is not mentioned in grounded_answer.\n"
    "- Do not invent facts not supported by search_results or grounded_answer.\n"
    "- Return ONLY valid JSON:\n"
    "\n"
    "{\n"
    "  \"brand\": \"string\",\n"
    "  \"sector\": \"string\",\n"
    "  \"prompt\": \"string\",\n"
    "  \"intent\": \"informational | comparison | transactional | alternative_search\",\n"
    "  \"mention_context\": \"primary_recommendation | secondary_recommendation | "
    "comparison_candidate | alternative_option | competitor_only | not_mentioned\",\n"
    "  \"recommendation_reasoning\": \"string\",\n"
    "  \"reasoning_trace\": {\n"
    "    \"search_findings\": \"string\",\n"
    "    \"answer_findings\": \"string\",\n"
    "    \"brand_evaluation\": \"string\",\n"
    "    \"confidence\": 0.0\n"
    "  },\n"
    "  \"visibility_drivers\": {\n"
    "    \"product_strength\": [\"string\"],\n"
    "    \"distribution_strength\": [\"string\"],\n"
    "    \"trust_strength\": [\"string\"],\n"
    "    \"brand_strength\": [\"string\"],\n"
    "    \"content_strength\": [\"string\"],\n"
    "    \"international_strength\": [\"string\"],\n"
    "    \"ux_strength\": [\"string\"]\n"
    "  },\n"
    "  \"visibility_gaps\": {\n"
    "    \"low_discoverability\": [\"string\"],\n"
    "    \"weak_ranking\": [\"string\"],\n"
    "    \"category_mismatch\": [\"string\"],\n"
    "    \"weak_trust_signals\": [\"string\"],\n"
    "    \"weak_feature_association\": [\"string\"],\n"
    "    \"competitor_dominance\": [\"string\"],\n"
    "    \"content_gap\": [\"string\"],\n"
    "    \"international_positioning_gap\": [\"string\"],\n"
    "    \"ux_positioning_gap\": [\"string\"],\n"
    "    \"reputation_gap\": [\"string\"]\n"
    "  },\n"
    "  \"trust_signals\": [\"string\"],\n"
    "  \"entities_associated_with_brand\": [\"string\"],\n"
    "  \"sentiment\": \"positive | neutral | negative\",\n"
    "  \"content_improvement_opportunities\": [\"string\"]\n"
    "}\n"
    "\n"
    "Use predefined visibility_gaps keys exactly. Empty categories stay as empty arrays.\n"
    "Maximum 3 items per drivers/gaps category. Maximum 5 trust_signals.\n"
    ""
)



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


class SearchClient(Protocol):
    def search(self, query: str, *, max_results: int = 5) -> dict[str, Any]: ...


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


def _text_mentions_brand(text: str, brand: str, aliases: list[str] | None = None) -> bool:
    if not text:
        return False
    terms = [brand, *(aliases or [])]
    lower = text.lower()
    for term in terms:
        cleaned = (term or "").strip()
        if len(cleaned) < 2:
            continue
        if re.search(r"\b" + re.escape(cleaned) + r"\b", lower, re.IGNORECASE):
            return True
    return False


def _find_brands_in_text(
    text: str, known_brands: list[str], *, exclude_brand: str | None = None
) -> list[str]:
    found: list[str] = []
    lower_text = (text or "").lower()
    exclude = (exclude_brand or "").lower()
    for brand in known_brands:
        if brand.lower() == exclude:
            continue
        if brand.lower() in lower_text and brand not in found:
            found.append(brand)
    return found


def _ensure_visibility_gaps(gaps: dict | None) -> dict[str, list]:
    merged = deepcopy(DEFAULT_VISIBILITY_GAPS)
    if gaps:
        for key in merged:
            merged[key] = list(gaps.get(key) or [])
    return merged


def _ensure_visibility_drivers(drivers: dict | None) -> dict[str, list]:
    merged = deepcopy(DEFAULT_VISIBILITY_DRIVERS)
    if drivers:
        for key in merged:
            merged[key] = list(drivers.get(key) or [])
    return merged


def _append_unique(items: list[str], message: str) -> None:
    if message and message not in items:
        items.append(message)


def annotate_brands_in_results(
    search_payload: dict[str, Any], known_brands: list[str]
) -> dict[str, Any]:
    for result in search_payload.get("results", []):
        if result.get("brands_mentioned"):
            continue
        result["brands_mentioned"] = _find_brands_in_text(
            f"{result.get('title', '')} {result.get('snippet', '')}",
            known_brands,
        )
    return search_payload


def measure_search_visibility(
    brand: str,
    search_payload: dict[str, Any],
    *,
    owned_domains: list[str],
    aliases: list[str] | None = None,
) -> dict[str, Any]:
    brand_lower = brand.lower()
    matching_results: list[int] = []
    title_mentions = 0
    snippet_mentions = 0
    owned_domain_in_results = False
    competitor_result_share: dict[str, int] = {}

    for result in search_payload.get("results", []):
        title = result.get("title", "")
        snippet = result.get("snippet", "")
        domain = result.get("domain", "")
        brands_in_result = result.get("brands_mentioned", [])

        brand_in_result = (
            _text_mentions_brand(title, brand, aliases)
            or _text_mentions_brand(snippet, brand, aliases)
            or any(b.lower() == brand_lower for b in brands_in_result)
            or _is_owned_domain(owned_domains, domain)
        )

        if brand_in_result:
            matching_results.append(int(result.get("rank") or 0))
            if _text_mentions_brand(title, brand, aliases):
                title_mentions += 1
            if _text_mentions_brand(snippet, brand, aliases):
                snippet_mentions += 1
            if _is_owned_domain(owned_domains, domain):
                owned_domain_in_results = True

        for competitor in brands_in_result:
            if competitor.lower() == brand_lower:
                continue
            competitor_result_share[competitor] = competitor_result_share.get(competitor, 0) + 1

    return {
        "brand_in_results": len(matching_results) > 0,
        "brand_result_count": len(matching_results),
        "brand_best_rank": min(matching_results) if matching_results else 0,
        "brand_result_ranks": matching_results,
        "title_mention_count": title_mentions,
        "snippet_mention_count": snippet_mentions,
        "owned_domain_in_results": owned_domain_in_results,
        "competitor_result_share": competitor_result_share,
        "total_results": search_payload.get("result_count", 0),
    }


def _format_search_results_for_prompt(search_payload: dict[str, Any]) -> str:
    lines = []
    for result in search_payload.get("results", []):
        lines.append(
            f"[{result['rank']}] {result['title']}\n"
            f"URL: {result['url']}\n"
            f"Domain: {result['domain']}\n"
            f"Snippet: {result['snippet']}\n"
            f"Brands mentioned: {', '.join(result.get('brands_mentioned', [])) or 'none'}"
        )
    return "\n\n".join(lines)


def call_grounded_answer(
    llm: ChatLLM, prompt: str, search_payload: dict[str, Any]
) -> dict[str, Any]:
    user_content = (
        f"User query: {prompt}\n\n"
        f"Search results:\n{_format_search_results_for_prompt(search_payload)}"
    )
    try:
        result = llm.chat(
            [
                {"role": "system", "content": GROUNDED_ANSWER_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            max_tokens=3000,
            json_object=True,
        )
        parsed, response_format = parse_llm_json(result.text)
        parsed["response_format"] = response_format
        parsed["error"] = False
        parsed["_cost_usd"] = float(getattr(result, "cost_usd", 0) or 0)
        return parsed
    except Exception as exc:  # noqa: BLE001 — surface as audit error record
        return {"error": True, "error_response": str(exc), "stage": "grounded_answer"}


def _build_result_lookup(search_payload: dict[str, Any]) -> dict[int, dict]:
    return {int(result["rank"]): result for result in search_payload.get("results", [])}


def normalize_grounded_citations(
    brand: str,
    grounded_payload: dict[str, Any],
    search_payload: dict[str, Any],
    *,
    owned_domains: list[str],
    aliases: list[str] | None = None,
) -> dict[str, Any]:
    lookup = _build_result_lookup(search_payload)
    brand_lower = brand.lower()
    citations = []

    for index, citation in enumerate(grounded_payload.get("citations") or [], start=1):
        rank = citation.get("result_rank") or citation.get("citation_position") or index
        source = lookup.get(int(rank), {})
        domain = citation.get("source_domain") or source.get("domain", "")
        title = citation.get("source_title") or source.get("title", "")
        url = citation.get("url") or source.get("url", "")
        brands_referenced = citation.get("brands_referenced") or source.get("brands_mentioned", [])
        mentions_target = (
            _text_mentions_brand(title, brand, aliases)
            or _text_mentions_brand(url, brand, aliases)
            or any(b.lower() == brand_lower for b in brands_referenced)
            or _is_owned_domain(owned_domains, domain)
        )
        citations.append(
            {
                "result_rank": rank,
                "source_title": title,
                "source_domain": domain,
                "source_type": citation.get("source_type", "other"),
                "url": url,
                "brands_referenced": brands_referenced,
                "mentions_target_brand": mentions_target,
                "citation_position": citation.get("citation_position") or index,
                "evidence_source": "search_result",
            }
        )

    grounded_payload["citations"] = citations
    return grounded_payload


def measure_answer_visibility(
    brand: str,
    grounded_payload: dict[str, Any],
    *,
    owned_domains: list[str],
    known_competitors: list[str],
    aliases: list[str] | None = None,
) -> dict[str, Any]:
    answer = grounded_payload.get("grounded_answer", "")
    brand_lower = brand.lower()
    mentioned = _text_mentions_brand(answer, brand, aliases)

    competitors: list[str] = []
    raw_competitors = grounded_payload.get("competitors") or _find_brands_in_text(
        answer, known_competitors, exclude_brand=brand
    )
    for competitor in raw_competitors:
        if competitor.lower() != brand_lower and competitor not in competitors:
            competitors.append(competitor)

    rank_position = 0
    if mentioned:
        positions = []
        for match in re.finditer(r"\b\w[\w\s&.-]{0,30}\b", answer):
            window = answer[match.start() : match.start() + 120].lower()
            if any((term or "").lower() in window for term in [brand, *(aliases or [])] if term):
                positions.append(match.start())
        if positions:
            earlier_competitors = []
            for competitor in competitors:
                competitor_index = answer.lower().find(competitor.lower())
                if competitor_index != -1 and competitor_index < positions[0]:
                    earlier_competitors.append(competitor)
            rank_position = len(earlier_competitors) + 1

    citations = grounded_payload.get("citations") or []
    target_citations = [c for c in citations if c.get("mentions_target_brand")]
    citation_positions = [
        c.get("citation_position", 0) for c in target_citations if c.get("citation_position", 0) > 0
    ]

    competitor_citation_share: dict[str, int] = {}
    for citation in citations:
        for referenced_brand in citation.get("brands_referenced", []):
            if referenced_brand.lower() == brand_lower:
                continue
            competitor_citation_share[referenced_brand] = (
                competitor_citation_share.get(referenced_brand, 0) + 1
            )

    return {
        "mentioned": mentioned,
        "rank_position": rank_position if mentioned else 0,
        "competitors": competitors,
        "citation_metrics": {
            "total_citations": len(citations),
            "target_brand_cited": len(target_citations) > 0,
            "target_brand_citation_count": len(target_citations),
            "target_brand_citation_rank": (min(citation_positions) if citation_positions else 0),
            "owned_media_cited": any(
                _is_owned_domain(owned_domains, citation.get("source_domain", ""))
                for citation in target_citations
            ),
            "earned_media_cited": any(
                not _is_owned_domain(owned_domains, citation.get("source_domain", ""))
                for citation in target_citations
            ),
            "competitor_citation_share": competitor_citation_share,
        },
    }


def call_audit_extraction(
    llm: ChatLLM,
    brand: str,
    prompt: str,
    prompt_group: str,
    search_payload: dict[str, Any],
    search_visibility: dict[str, Any],
    grounded_payload: dict[str, Any],
    answer_visibility: dict[str, Any],
) -> dict[str, Any]:
    evidence = {
        "target_brand": brand,
        "prompt": prompt,
        "prompt_group": prompt_group,
        "search_visibility": search_visibility,
        "answer_visibility": answer_visibility,
        "search_results": search_payload.get("results", []),
        "grounded_answer": grounded_payload.get("grounded_answer", ""),
        "citations": grounded_payload.get("citations", []),
    }
    try:
        result = llm.chat(
            [
                {"role": "system", "content": AUDIT_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(evidence, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=3500,
            json_object=True,
        )
        parsed, response_format = parse_llm_json(result.text)
        parsed["response_format"] = response_format
        parsed["error"] = False
        parsed["_cost_usd"] = float(getattr(result, "cost_usd", 0) or 0)
        return parsed
    except Exception as exc:  # noqa: BLE001
        return {
            "error": True,
            "error_response": str(exc),
            "stage": "audit_extraction",
        }


def merge_measured_record(
    brand: str,
    prompt: str,
    prompt_group: str,
    model: str,
    search_payload: dict[str, Any],
    search_visibility: dict[str, Any],
    grounded_payload: dict[str, Any],
    answer_visibility: dict[str, Any],
    audit_payload: dict[str, Any],
    *,
    owned_domains: list[str],
    sector: str = "",
) -> dict[str, Any]:
    grounded_answer = grounded_payload.get("grounded_answer", "")
    mentioned = answer_visibility.get("mentioned", False)
    visibility_gaps = _ensure_visibility_gaps(audit_payload.get("visibility_gaps"))
    visibility_drivers = _ensure_visibility_drivers(audit_payload.get("visibility_drivers"))

    if not search_visibility.get("brand_in_results"):
        _append_unique(
            visibility_gaps["low_discoverability"],
            f"{brand} did not appear in the top "
            f"{search_visibility.get('total_results', 0)} web search results.",
        )
    if not mentioned:
        visibility_drivers = deepcopy(DEFAULT_VISIBILITY_DRIVERS)
        _append_unique(
            visibility_gaps["low_discoverability"],
            f"{brand} was not mentioned in the grounded answer.",
        )
    if search_visibility.get("competitor_result_share"):
        top_competitors = sorted(
            search_visibility["competitor_result_share"].items(),
            key=lambda item: item[1],
            reverse=True,
        )[:5]
        _append_unique(
            visibility_gaps["competitor_dominance"],
            "Search results favored: "
            + ", ".join(f"{name} ({count})" for name, count in top_competitors)
            + ".",
        )
    if mentioned and not answer_visibility["citation_metrics"].get("target_brand_cited"):
        _append_unique(
            visibility_gaps["content_gap"],
            f"{brand} was mentioned in the grounded answer but not supported "
            "by cited search results.",
        )
    if not search_visibility.get("owned_domain_in_results"):
        domains_label = ", ".join(owned_domains) or "unknown"
        _append_unique(
            visibility_gaps["content_gap"],
            f"No owned-domain result ({domains_label}) appeared in search results.",
        )

    mention_context = audit_payload.get("mention_context", "not_mentioned")
    if not mentioned:
        mention_context = "not_mentioned"

    return {
        "brand": brand,
        "sector": sector or audit_payload.get("sector") or "",
        "prompt": prompt,
        "prompt_group": prompt_group,
        "intent": audit_payload.get("intent", "informational"),
        "measurement_mode": search_payload.get("search_mode"),
        "search_provider": search_payload.get("search_provider"),
        "search_results": search_payload.get("results", []),
        "search_visibility": search_visibility,
        "grounded_answer": grounded_answer,
        "simulated_answer": grounded_answer,
        "mentioned": mentioned,
        "rank_position": answer_visibility.get("rank_position", 0),
        "mention_context": mention_context,
        "competitors": answer_visibility.get("competitors", []),
        "answer_summary": grounded_payload.get("answer_summary")
        or audit_payload.get("answer_summary", ""),
        "recommendation_reasoning": audit_payload.get("recommendation_reasoning", ""),
        "reasoning_trace": audit_payload.get("reasoning_trace", {}),
        "citations": grounded_payload.get("citations", []),
        "citation_metrics": answer_visibility.get(
            "citation_metrics", deepcopy(DEFAULT_CITATION_METRICS)
        ),
        "visibility_drivers": visibility_drivers,
        "visibility_gaps": visibility_gaps,
        "trust_signals": audit_payload.get("trust_signals", []),
        "entities_associated_with_brand": audit_payload.get("entities_associated_with_brand", []),
        "sentiment": audit_payload.get("sentiment", "neutral"),
        "content_improvement_opportunities": audit_payload.get(
            "content_improvement_opportunities", []
        ),
        "model": model,
        "generated_at": datetime.now(UTC).isoformat(),
        "error": False,
        "schema_version": SCHEMA_VERSION,
        "owned_domains": owned_domains,
        # What this one audit cost, summed from the calls that produced it. Each
        # stage already knew its own price and, until session 21, every one of
        # them was thrown away here — so `responses.cost_usd` was 0 on the live
        # default path and the daily USD cap that sums that column could never
        # trip. The search leg is added by the caller, which is the only place
        # that knows whether a search actually happened.
        "_cost_usd": _call_cost(grounded_payload) + _call_cost(audit_payload),
    }


def _call_cost(payload: dict[str, Any] | None) -> float:
    """The dollar cost a single provider call reported, defaulting to 0.

    Defensive by design: an error payload from a failed stage carries no
    ``_cost_usd`` key, and a stage that never ran carries nothing at all.
    Neither should make the sum explode — but note a failed call may still have
    been billed, which is why the error paths record what they spent rather than
    resetting to zero.
    """

    if not payload:
        return 0.0
    try:
        return float(payload.get("_cost_usd") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def mock_grounded_and_audit(
    brand: str,
    prompt: str,
    prompt_group: str,
    search_payload: dict[str, Any],
    *,
    owned_domains: list[str],
    aliases: list[str] | None = None,
    known_competitors: list[str] | None = None,
    sector: str = "",
) -> dict[str, Any]:
    """Deterministic grounded + audit payloads for DRY_RUN (no LLM)."""
    mentioned = any(
        _text_mentions_brand(f"{r.get('title', '')} {r.get('snippet', '')}", brand, aliases)
        or _is_owned_domain(owned_domains, r.get("domain", ""))
        for r in search_payload.get("results", [])
    )
    citations = []
    for result in search_payload.get("results", [])[:3]:
        citations.append(
            {
                "result_rank": result["rank"],
                "source_title": result["title"],
                "source_domain": result["domain"],
                "url": result["url"],
                "source_type": "review",
                "brands_referenced": result.get("brands_mentioned", []),
                "citation_position": result["rank"],
            }
        )
    answer = (
        f"{brand} is a strong option based on the search results [1]. "
        f"Other names that appear include Acme and Globex."
        if mentioned
        else "Category leaders in the search results include Acme and Globex [2]."
    )
    grounded = {
        "grounded_answer": answer,
        "citations": citations,
        "competitors": ["Acme", "Globex"],
        "answer_summary": "Mock grounded answer.",
        "error": False,
        "_cost_usd": 0.0,
    }
    search_visibility = measure_search_visibility(
        brand, search_payload, owned_domains=owned_domains, aliases=aliases
    )
    grounded = normalize_grounded_citations(
        brand,
        grounded,
        search_payload,
        owned_domains=owned_domains,
        aliases=aliases,
    )
    answer_visibility = measure_answer_visibility(
        brand,
        grounded,
        owned_domains=owned_domains,
        known_competitors=known_competitors or ["Acme", "Globex"],
        aliases=aliases,
    )
    audit: dict[str, Any] = {
        "intent": "informational",
        "mention_context": ("primary_recommendation" if mentioned else "not_mentioned"),
        "recommendation_reasoning": "Mock audit reasoning.",
        "reasoning_trace": {
            "search_findings": "mock",
            "answer_findings": "mock",
            "brand_evaluation": "mock",
            "confidence": 0.9,
        },
        "visibility_drivers": deepcopy(DEFAULT_VISIBILITY_DRIVERS),
        "visibility_gaps": deepcopy(DEFAULT_VISIBILITY_GAPS),
        "trust_signals": [],
        "entities_associated_with_brand": [],
        "sentiment": "neutral",
        "content_improvement_opportunities": [],
        "error": False,
        "_cost_usd": 0.0,
    }
    if mentioned:
        drivers = audit["visibility_drivers"]
        assert isinstance(drivers, dict)
        drivers["brand_strength"] = [f"{brand} appears in grounded answer."]
    return merge_measured_record(
        brand,
        prompt,
        prompt_group,
        "mock",
        search_payload,
        search_visibility,
        grounded,
        answer_visibility,
        audit,
        owned_domains=owned_domains,
        sector=sector,
    )


def run_measured_audit(
    *,
    brand: str,
    prompt: str,
    prompt_group: str,
    owned_domains: list[str],
    aliases: list[str] | None = None,
    known_competitors: list[str] | None = None,
    sector: str = "",
    llm: ChatLLM | None = None,
    search: SearchClient | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run one measured audit for ``(brand, prompt)``.

    When ``dry_run`` is True, uses mock search + mock grounded/audit (no keys).
    """
    known = list(known_competitors or [])
    for name in [brand, *(aliases or [])]:
        if name and name not in known:
            known.append(name)

    if dry_run or search is None:
        search_payload = mock_search(prompt, brand=brand)
    else:
        search_payload = search.search(prompt)

    search_payload = annotate_brands_in_results(search_payload, known)
    # The search is billed the moment it returns, whatever happens downstream —
    # so it is carried separately and added to every exit path below, including
    # the error ones. A failed audit that already paid for a search must not
    # report $0.
    search_cost = _call_cost(search_payload)

    if dry_run or llm is None:
        return mock_grounded_and_audit(
            brand,
            prompt,
            prompt_group,
            search_payload,
            owned_domains=owned_domains,
            aliases=aliases,
            known_competitors=known_competitors,
            sector=sector,
        )

    search_visibility = measure_search_visibility(
        brand, search_payload, owned_domains=owned_domains, aliases=aliases
    )
    grounded_payload = call_grounded_answer(llm, prompt, search_payload)
    if grounded_payload.get("error"):
        return {
            "model": getattr(llm, "model", ""),
            "brand": brand,
            "prompt": prompt,
            "prompt_group": prompt_group,
            "error": True,
            "error_stage": grounded_payload.get("stage"),
            "error_response": grounded_payload.get("error_response"),
            "search_results": search_payload.get("results", []),
            "search_visibility": search_visibility,
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "mentioned": False,
            "mention_context": "not_mentioned",
            "citation_metrics": deepcopy(DEFAULT_CITATION_METRICS),
            "sentiment": "neutral",
            "_cost_usd": search_cost + _call_cost(grounded_payload),
        }

    grounded_payload = normalize_grounded_citations(
        brand,
        grounded_payload,
        search_payload,
        owned_domains=owned_domains,
        aliases=aliases,
    )
    answer_visibility = measure_answer_visibility(
        brand,
        grounded_payload,
        owned_domains=owned_domains,
        known_competitors=known_competitors or [],
        aliases=aliases,
    )
    audit_payload = call_audit_extraction(
        llm,
        brand,
        prompt,
        prompt_group,
        search_payload,
        search_visibility,
        grounded_payload,
        answer_visibility,
    )
    if audit_payload.get("error"):
        return {
            "model": getattr(llm, "model", ""),
            "brand": brand,
            "prompt": prompt,
            "prompt_group": prompt_group,
            "error": True,
            "error_stage": audit_payload.get("stage"),
            "error_response": audit_payload.get("error_response"),
            "search_results": search_payload.get("results", []),
            "search_visibility": search_visibility,
            "grounded_answer": grounded_payload.get("grounded_answer"),
            "mentioned": answer_visibility.get("mentioned", False),
            "mention_context": (
                "not_mentioned"
                if not answer_visibility.get("mentioned")
                else "secondary_recommendation"
            ),
            "citation_metrics": answer_visibility.get(
                "citation_metrics", deepcopy(DEFAULT_CITATION_METRICS)
            ),
            "sentiment": "neutral",
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "_cost_usd": (
                search_cost + _call_cost(grounded_payload) + _call_cost(audit_payload)
            ),
        }

    record = merge_measured_record(
        brand,
        prompt,
        prompt_group,
        getattr(llm, "model", ""),
        search_payload,
        search_visibility,
        grounded_payload,
        answer_visibility,
        audit_payload,
        owned_domains=owned_domains,
        sector=sector,
    )
    record["_cost_usd"] = _call_cost(record) + search_cost
    return record
