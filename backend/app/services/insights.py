"""Read-time visibility insights over stored analysis answers.

The helper is deliberately pure: it consumes prompt/response-like rows plus the
KYC JSON and returns frozen dataclasses. Brand-probe prompts are withheld from
the scored denominator because they name the company in the question.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from math import ceil
from typing import Any, Literal, Protocol

from app.services.checker_summary import brand_exclusions, names_in_answer

BRAND_PROBE = "brand-probe"
INTENT_GROUPS: dict[str, tuple[str, ...]] = {
    "discovery": ("makers", "best-of"),
    "comparison": ("comparison", "alternatives"),
    "recommendation": ("recommendation", "use-case"),
}
_ORDERED_CATEGORIES = [
    "makers",
    "best-of",
    "comparison",
    "alternatives",
    "recommendation",
    "use-case",
]

Ownership = Literal["ours", "shared", "competitor", "unclaimed"]
Tier = Literal["core", "secondary", "none"]
Presence = Literal["present", "high-impact-missing", "missing"]


class PromptLike(Protocol):
    id: Any
    text: str
    category: str


class ResponseLike(Protocol):
    prompt_id: Any
    engine: str
    footprint: bool | None
    raw_text: str


@dataclass(frozen=True)
class Ratio:
    mentioned: int
    total: int


@dataclass(frozen=True)
class IntentGroupStat(Ratio):
    group: str


@dataclass(frozen=True)
class CompetitorMention:
    name: str
    answers: int


@dataclass(frozen=True)
class EngineInsight(Ratio):
    engine: str
    groups: list[IntentGroupStat] = field(default_factory=list)
    brandAnswers: int = 0
    competitors: list[CompetitorMention] = field(default_factory=list)
    share: float | None = None
    firstMentions: int = 0


@dataclass(frozen=True)
class CategoryGap:
    category: str
    total: int
    lost: int
    competitors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VisibilityGap:
    answersLost: int
    total: int
    categories: list[CategoryGap] = field(default_factory=list)


@dataclass(frozen=True)
class EntityStat:
    name: str
    answers: int
    ownership: Ownership
    tier: Tier
    presence: Presence | None = None


@dataclass(frozen=True)
class EntityCoverage:
    present: int
    total: int
    entities: list[EntityStat] = field(default_factory=list)


@dataclass(frozen=True)
class EntityLandscape:
    coreThreshold: int
    entities: list[EntityStat] = field(default_factory=list)


@dataclass(frozen=True)
class DriverStat(Ratio):
    category: str
    contribution: float


@dataclass(frozen=True)
class Insights:
    brand: str
    subject: str
    promptSet: str
    scoredAnswers: int
    probe: Ratio | None
    engines: list[EngineInsight] = field(default_factory=list)
    gap: VisibilityGap = field(default_factory=lambda: VisibilityGap(0, 0))
    entityCoverage: EntityCoverage = field(default_factory=lambda: EntityCoverage(0, 0))
    entityLandscape: EntityLandscape = field(
        default_factory=lambda: EntityLandscape(0)
    )
    drivers: list[DriverStat] = field(default_factory=list)


def _brand(kyc: dict[str, Any] | None) -> str:
    value = (kyc or {}).get("company")
    return value.strip() if isinstance(value, str) and value.strip() else "Brand"


def _subject(kyc: dict[str, Any] | None) -> str:
    if not kyc:
        return "analysis"
    for key in ("category", "industry", "description"):
        value = kyc.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "analysis"


def _entity_terms(kyc: dict[str, Any] | None) -> list[str]:
    if not kyc:
        return []
    terms: list[str] = []
    for key in ("products", "services", "keywords", "locations", "use_cases"):
        values = kyc.get(key)
        if isinstance(values, list):
            terms.extend(v.strip() for v in values if isinstance(v, str) and v.strip())
    category = kyc.get("category")
    if isinstance(category, str) and category.strip():
        terms.append(category.strip())
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        folded = term.casefold()
        if folded not in seen:
            seen.add(folded)
            unique.append(term)
    return unique


def _contains(text: str, name: str) -> bool:
    return re.search(
        rf"(?<!\w){re.escape(name)}(?!\w)",
        text or "",
        flags=re.IGNORECASE,
    ) is not None


def _answer_count(rows: list[ResponseLike], name: str) -> int:
    return sum(1 for row in rows if _contains(row.raw_text, name))


def _first_brand_index(text: str, exclusions: set[str]) -> int | None:
    folded = (text or "").casefold()
    positions = [folded.find(name) for name in exclusions if name and folded.find(name) >= 0]
    return min(positions) if positions else None


def _tier(answers: int, core_threshold: int) -> Tier:
    if answers >= core_threshold and answers > 0:
        return "core"
    if answers > 0:
        return "secondary"
    return "none"


def summarize_insights(
    responses: Sequence[ResponseLike],
    prompts: Sequence[PromptLike],
    kyc: dict[str, Any] | None,
    prompt_set: str = "mvp",
) -> Insights | None:
    prompt_by_id = {prompt.id: prompt for prompt in prompts}
    scored: list[tuple[ResponseLike, PromptLike]] = []
    probes: list[ResponseLike] = []
    for response in responses:
        prompt = prompt_by_id.get(response.prompt_id)
        if prompt is None:
            continue
        if prompt.category == BRAND_PROBE:
            probes.append(response)
        else:
            scored.append((response, prompt))

    if not scored:
        return None

    rows = [row for row, _prompt in scored]
    exclusions = brand_exclusions(kyc)
    all_competitors = [names_in_answer(row.raw_text, exclusions) for row in rows]
    competitor_counts: Counter[str] = Counter()
    competitor_display: dict[str, str] = {}
    for names in all_competitors:
        for name in names:
            key = name.casefold()
            competitor_counts[key] += 1
            competitor_display.setdefault(key, name)

    engine_order = list(dict.fromkeys(row.engine for row in rows))
    engines: list[EngineInsight] = []
    for engine in engine_order:
        engine_pairs = [(row, prompt) for row, prompt in scored if row.engine == engine]
        engine_rows = [row for row, _prompt in engine_pairs]
        engine_competitors = [names_in_answer(row.raw_text, exclusions) for row in engine_rows]
        engine_competitor_counts: Counter[str] = Counter()
        engine_display: dict[str, str] = {}
        for names in engine_competitors:
            for name in names:
                key = name.casefold()
                engine_competitor_counts[key] += 1
                engine_display.setdefault(key, name)
        competitor_answers = sum(1 for names in engine_competitors if names)
        brand_answers = sum(1 for row in engine_rows if row.footprint)
        share_base = brand_answers + competitor_answers
        first_mentions = 0
        for row, names in zip(engine_rows, engine_competitors, strict=False):
            brand_index = _first_brand_index(row.raw_text, exclusions)
            if brand_index is None:
                continue
            competitor_positions = [
                (row.raw_text or "").casefold().find(name.casefold()) for name in names
            ]
            if all(pos < 0 or brand_index < pos for pos in competitor_positions):
                first_mentions += 1
        groups = []
        for group, categories in INTENT_GROUPS.items():
            group_rows = [
                row for row, prompt in engine_pairs if prompt.category in categories
            ]
            groups.append(
                IntentGroupStat(
                    group=group,
                    mentioned=sum(1 for row in group_rows if row.footprint),
                    total=len(group_rows),
                )
            )
        ranked = sorted(engine_competitor_counts.items(), key=lambda item: (-item[1], item[0]))
        engines.append(
            EngineInsight(
                engine=engine,
                mentioned=brand_answers,
                total=len(engine_rows),
                groups=groups,
                brandAnswers=brand_answers,
                competitors=[
                    CompetitorMention(engine_display[key], count)
                    for key, count in ranked[:5]
                ],
                share=brand_answers / share_base if share_base else None,
                firstMentions=first_mentions,
            )
        )

    gap_categories: list[CategoryGap] = []
    for category in _ORDERED_CATEGORIES:
        category_rows = [
            row for row, prompt in scored if prompt.category == category
        ]
        lost_rows = [
            row
            for row in category_rows
            if not row.footprint and names_in_answer(row.raw_text, exclusions)
        ]
        category_competitors: Counter[str] = Counter()
        display: dict[str, str] = {}
        for row in lost_rows:
            for name in names_in_answer(row.raw_text, exclusions):
                key = name.casefold()
                category_competitors[key] += 1
                display.setdefault(key, name)
        ranked = sorted(category_competitors.items(), key=lambda item: (-item[1], item[0]))
        gap_categories.append(
            CategoryGap(
                category=category,
                total=len(category_rows),
                lost=len(lost_rows),
                competitors=[display[key] for key, _count in ranked[:3]],
            )
        )

    own_terms = _entity_terms(kyc)
    core_threshold = max(1, ceil(len(rows) * 0.5))
    own_entities: list[EntityStat] = []
    for term in own_terms:
        answers = _answer_count(rows, term)
        co_mentions = sum(
            1 for row in rows if row.footprint and _contains(row.raw_text, term)
        )
        ownership: Ownership = (
            "shared" if co_mentions else "competitor" if answers else "unclaimed"
        )
        presence: Presence = (
            "present"
            if co_mentions
            else "high-impact-missing"
            if answers
            else "missing"
        )
        own_entities.append(
            EntityStat(
                name=term,
                answers=answers,
                ownership=ownership,
                tier=_tier(answers, core_threshold),
                presence=presence,
            )
        )
    landscape_entities = [
        EntityStat(_brand(kyc), sum(1 for row in rows if row.footprint), "ours", "core")
    ]
    landscape_entities.extend(
        EntityStat(entity.name, entity.answers, entity.ownership, entity.tier)
        for entity in own_entities
        if entity.answers > 0
    )
    own_term_keys = {entity.name.casefold() for entity in own_entities}
    for key, count in sorted(competitor_counts.items(), key=lambda item: (-item[1], item[0])):
        # A KYC term can also look like a proper-name competitor (for example
        # a location such as "Turkey"). It already has an ownership-aware row
        # above, so do not append a second, contradictory competitor row.
        if key in own_term_keys:
            continue
        landscape_entities.append(
            EntityStat(competitor_display[key], count, "competitor", _tier(count, core_threshold))
        )

    category_mentions = {
        category: sum(
            1 for row, prompt in scored if prompt.category == category and row.footprint
        )
        for category in _ORDERED_CATEGORIES
    }
    total_brand_mentions = sum(category_mentions.values())
    probe = Ratio(sum(1 for row in probes if row.footprint), len(probes)) if probes else None

    return Insights(
        brand=_brand(kyc),
        subject=_subject(kyc),
        promptSet=prompt_set,
        scoredAnswers=len(rows),
        probe=probe,
        engines=engines,
        gap=VisibilityGap(
            answersLost=sum(row.lost for row in gap_categories),
            total=len(rows),
            categories=gap_categories,
        ),
        entityCoverage=EntityCoverage(
            present=sum(1 for entity in own_entities if entity.presence == "present"),
            total=len(own_entities),
            entities=own_entities,
        ),
        entityLandscape=EntityLandscape(
            coreThreshold=core_threshold,
            entities=sorted(
                landscape_entities,
                key=lambda entity: (-entity.answers, entity.name.casefold()),
            )[:20],
        ),
        drivers=[
            DriverStat(
                category=category,
                mentioned=mentioned,
                total=sum(1 for _row, prompt in scored if prompt.category == category),
                contribution=mentioned / total_brand_mentions if total_brand_mentions else 0,
            )
            for category, mentioned in category_mentions.items()
        ],
    )
