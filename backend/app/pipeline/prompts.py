"""Deterministic prompt generation from a KYC profile (no LLM).

GEO prompts simulate what real users ask AI engines, and real users ask about
product *categories* ("Who are the biggest FPV kamikaze drone manufacturers in
Türkiye?"), not about a vendor's private model names. So topics are split by
role:

* QUESTION TOPICS fill the recommendation/makers/comparison/alternatives/
  best-of/use-case slots. They are category-like phrases only, drawn in
  confidence order: the KYC's own ``category`` first, then ``use_cases``, then
  keywords that survive the category filter, then short services, then the
  leading industry segment. A company's own product/model names are NEVER used
  here (a "leading BAZNA V10 manufacturers" question is nonsense: BAZNA V10 is
  *their* model, not a category).
* PRODUCTS get their own dedicated ``brand-probe`` shapes ("What do you know
  about {product} from {company}?") — genuine questions that also test whether
  engines recognise the product. Brand probes are capped at ~1/4 of the output
  so category questions (the real visibility test) dominate.

Three properties this module is responsible for (docs/pipeline-quality-plan.md,
workstream P):

* **The category filter.** A model asked for "keywords" returns spec attributes
  ("payload capacity", "RPG-7 capability", "EW immune"). Conjugated into a
  question they read as nonsense and cost four paid calls each, so phrases with
  digits, symbols or attribute-noun tails are rejected outright. This is a noise
  filter, not a classifier — the real fix is ``KYC.category``, which asks for
  the category instead of inferring it.
* **Rotation that actually covers.** Category and topic advance on different
  strides, so every topic meets every shape before any pair repeats. (Walking
  both with the same index means a profile with exactly six topics only ever
  produces six distinct questions.)
* **No brand in the question.** A prompt outside ``brand-probe`` may never
  contain the company name or an alias — SEO copy routinely puts the brand in
  the keywords, and asking "What are the best <Brand> options?" and then
  counting the brand's appearance in the answers is a self-fulfilling score.
  Enforced on the topic pool *and* on the finished text.

The industry is used one segment at a time (the first comma/slash-separated
part, e.g. "Defense Technology", not the whole list), and over-long phrases are
kept out of slots where they read badly. Returns exactly ``count`` prompts, each
with non-empty text and a category, and never any duplicates. Templated prompts
are testable and free; LLM prompt generation is on the roadmap, not the MVP.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.pipeline.sanitize import clean_str, clean_values, contains, normalize_key
from app.pipeline.textfold import fold

# The six "category question" shapes, cycled in this order.
CATEGORIES = [
    "recommendation",
    "makers",
    "comparison",
    "alternatives",
    "best-of",
    "use-case",
]

# Products get their own shape under this (non-cycled) category.
BRAND_PROBE = "brand-probe"

# Longest phrase (in words) allowed as a question topic; longer ones read badly
# stuffed into "alternatives to X for {topic}" and similar slots.
_MAX_TOPIC_WORDS = 5
# Services longer than this are not category-like enough to be question topics.
_MAX_SERVICE_WORDS = 4
# Shorter than this is an initial or a typo, not a category.
_MIN_TOPIC_CHARS = 2
# Matches footprint's floor: a 1-character "alias" would leak-filter everything.
_MIN_BRAND_KEY_LEN = 2

# Nouns that end an *attribute* phrase rather than a category. "payload
# capacity" and "flight endurance" describe a product; they are not a kind of
# product, and "Who are the leading payload capacity manufacturers?" is the
# question that made this list necessary. Compared folded + casefolded.
_ATTRIBUTE_TAILS = frozenset(
    {
        "capacity",
        "capability",
        "capabilities",
        "endurance",
        "range",
        "weight",
        "size",
        "length",
        "height",
        "speed",
        "accuracy",
        "precision",
        "performance",
        "efficiency",
        "reliability",
        "durability",
        "immune",
        "immunity",
        "resistant",
        "resistance",
        "compliance",
        "compliant",
        "certified",
        "certification",
        "ready",
        "enabled",
        "based",
        "proof",
        "grade",
        "level",
        "quality",
        "support",
        "warranty",
        "price",
        "cost",
    }
)

# A single hyphenated token starting with one of these is an adjective, not a
# category ("anti-armor", "non-lethal", "high-precision"). Multi-word phrases
# are left alone — "multi-role aircraft" is a perfectly good category.
_MODIFIER_PREFIXES = frozenset(
    {"anti", "non", "semi", "ultra", "high", "low", "pre", "post", "self"}
)

# Symbols that mark a spec line rather than a category ("99.9% uptime", "R&D").
_BANNED_TOPIC_CHARS = frozenset("%+&/\\:;|<>=~^*")

# Things that get *manufactured* — the tell that "manufacturers" is the right
# noun for the makers slot. Deliberately concrete: the default is the neutral
# "companies", and this list only upgrades it.
_GOODS_WORDS = frozenset(
    {
        "drone", "drones", "uav", "uavs", "uas", "ugv", "ugvs", "iha", "ika",
        "vehicle", "vehicles", "robot", "robots", "robotics", "machine",
        "machines", "machinery", "equipment", "device", "devices", "hardware",
        "sensor", "sensors", "battery", "batteries", "engine", "engines",
        "aircraft", "helicopter", "helicopters", "munition", "munitions",
        "weapon", "weapons", "component", "components", "part", "parts",
        "tool", "tools", "system", "systems", "module", "modules", "furniture",
        "appliance", "appliances", "textile", "textiles", "packaging",
        "chemical", "chemicals", "steel", "cable", "cables", "pump", "pumps",
        "valve", "valves", "motor", "motors", "panel", "panels", "turbine",
        "turbines", "instrument", "instruments", "camera", "cameras",
        "antenna", "antennas", "furnace", "boiler", "boilers", "tractor",
        "tractors", "truck", "trucks", "bike", "bikes", "shoe", "shoes",
    }
)

# Words that veto "manufacturers" even when a goods word is present ("software
# systems" is not manufactured). Checked first.
_INTANGIBLE_WORDS = frozenset(
    {
        "software", "platform", "platforms", "app", "apps", "saas", "cloud",
        "api", "apis", "crm", "erp", "website", "websites", "agency",
        "consulting", "consultancy", "marketing", "analytics", "service",
        "services", "solution", "solutions", "support", "training",
        "insurance", "banking", "logistics", "hosting", "data",
    }
)

# Curious-user questions about a specific product that also probe brand
# recognition; each names both the product and the company.
_BRAND_PROBES = [
    "How does {product} by {company} compare to similar products on the market?",
    "What do you know about {product} from {company}?",
]

# Natural padders (used only when a sparse KYC runs out of distinct templates).
_PADDERS = [
    "Which providers are known for excellent {topic}?",
    "What should buyers look for when choosing {topic}?",
    "Who offers the most reliable {topic} today?",
    "What sets a great {topic} provider apart?",
    "Which brands lead the market for {topic}?",
    "How should someone evaluate different {topic} options?",
]

# Topic kinds. The kind decides the verb: you ask who *manufactures* industrial
# robots and who *provides* systems integration, and getting that backwards is
# the tell that a question was generated rather than asked.
_KIND_CATEGORY = "category"
_KIND_SERVICE = "service"


@dataclass(frozen=True)
class PromptSpec:
    text: str
    category: str


@dataclass(frozen=True)
class Topic:
    """One question subject plus where it came from."""

    text: str
    kind: str = _KIND_CATEGORY


def _clean_list(values) -> list[str]:
    """Trimmed, de-duplicated, junk-free list (generous caps; see sanitize)."""
    return clean_values(values, max_items=25, max_chars=120)


def _first_segment(value: str) -> str:
    """The leading comma/slash-separated segment, trimmed.

    "Defense Technology, Unmanned Systems, AI" -> "Defense Technology".
    """
    value = clean_str(value, max_chars=120)
    if not value:
        return ""
    return re.split(r"\s*[,/]\s*", value)[0].strip()


def _word_count(phrase: str) -> int:
    return len(phrase.split())


def _is_category_like(phrase: str) -> bool:
    """True when a phrase can plausibly name a category people shop for.

    Rejects the four shapes a "keyword" field routinely carries that a question
    slot cannot survive: model codes and specs (digits), spec-sheet symbols,
    attribute phrases ("payload capacity"), and bare hyphenated adjectives
    ("anti-armor").
    """
    phrase = phrase.strip()
    words = phrase.split()
    if not words or len(phrase) < _MIN_TOPIC_CHARS:
        return False
    if not 1 <= len(words) <= _MAX_TOPIC_WORDS:
        return False
    if any(char.isdigit() for char in phrase):
        return False
    if any(char in _BANNED_TOPIC_CHARS for char in phrase):
        return False
    if fold(words[-1]).strip(".,'\"") in _ATTRIBUTE_TAILS:
        return False
    if len(words) == 1 and "-" in phrase:
        if fold(phrase).split("-", 1)[0] in _MODIFIER_PREFIXES:
            return False
    return True


def _brand_keys(kyc) -> list[str]:
    """Normalized forms of the company name and its aliases.

    Anything shorter than ``_MIN_BRAND_KEY_LEN`` is dropped for the same reason
    ``footprint`` drops it: a one-character key matches everything.
    """
    keys: set[str] = set()
    for name in [getattr(kyc, "company", ""), *(getattr(kyc, "aliases", []) or [])]:
        cleaned = clean_str(name, max_chars=120)
        if len(cleaned) < _MIN_BRAND_KEY_LEN:
            continue
        key = normalize_key(cleaned)
        if key:
            keys.add(key)
    return sorted(keys)


def _leaks_brand(text: str, brand_keys: list[str]) -> bool:
    """True when a question names the very brand it is supposed to measure."""
    haystack = normalize_key(text)
    return any(contains(haystack, key) for key in brand_keys)


def topic_pool(kyc, max_words: int = _MAX_TOPIC_WORDS) -> list[Topic]:
    """Category-like subjects for the question slots — never product names.

    Confidence order: ``category`` (the field that exists precisely so this is
    not a guess), then ``use_cases``, then keywords that survive
    :func:`_is_category_like`, then short services, then the leading industry
    segment. Topics naming the company are dropped — see the module docstring.
    """
    candidates: list[Topic] = []
    category = clean_str(getattr(kyc, "category", ""), max_chars=60)
    if category:
        candidates.append(Topic(category))
    candidates += [Topic(value) for value in _clean_list(getattr(kyc, "use_cases", []))]
    candidates += [Topic(value) for value in _clean_list(kyc.keywords)]
    candidates += [
        Topic(value, _KIND_SERVICE)
        for value in _clean_list(kyc.services)
        if _word_count(value) <= _MAX_SERVICE_WORDS
    ]
    industry = _first_segment(kyc.industry)
    if industry:
        candidates.append(Topic(industry))

    brand_keys = _brand_keys(kyc)
    pool: list[Topic] = []
    seen: set[str] = set()
    for topic in candidates:
        key = normalize_key(topic.text)
        if not key or key in seen:
            continue
        if _word_count(topic.text) > max_words or not _is_category_like(topic.text):
            continue
        if _leaks_brand(topic.text, brand_keys):
            continue
        seen.add(key)
        pool.append(topic)
    return pool


def _question_topics(kyc) -> list[Topic]:
    """The topic pool, with the neutral fallback when a profile yields none."""
    pool = topic_pool(kyc)
    return pool or [Topic("solutions")]


def _maker_noun(topic: Topic) -> str:
    """"manufacturers" / "providers" / "companies" for the makers-style slots.

    Decided by the **head noun** — the last word — because that is what an
    English noun phrase is actually about: "ISR systems" names a thing that is
    manufactured, while "system integration" names an activity that is
    provided, and the two share a word. Anything unrecognised falls back to the
    neutral "companies" rather than guessing.
    """
    words = topic.text.split()
    head = fold(words[-1]) if words else ""
    if head in _INTANGIBLE_WORDS:
        return "providers" if topic.kind == _KIND_SERVICE else "companies"
    if head in _GOODS_WORDS:
        return "manufacturers"
    if topic.kind == _KIND_SERVICE:
        return "providers"
    return "companies"


def _is_plural(topic: Topic) -> bool:
    """Whether the head noun already names more than one thing.

    Decides between "the best tactical UAVs available" and "the best unmanned
    aerial vehicle *options* available" — the padding noun is what keeps a
    singular topic grammatical, and what makes a plural one read like a machine
    wrote it.
    """
    words = topic.text.split()
    if not words:
        return False
    head = fold(words[-1])
    return len(head) > 2 and head.endswith("s") and not head.endswith("ss")


@dataclass(frozen=True)
class _Context:
    """The per-run values every template slot may substitute."""

    industry: str
    location: str
    competitor: str


def _context(kyc) -> _Context:
    locations = _clean_list(kyc.locations)
    competitors = _clean_list(kyc.competitors)
    return _Context(
        industry=_first_segment(kyc.industry),
        location=f"in {locations[0]}" if locations else "worldwide",
        competitor=competitors[0] if competitors else "the market leaders",
    )


def _shapes(category: str, topic: Topic, ctx: _Context) -> list[str]:
    """The phrasings available for one (category, topic) pair, best first.

    More than one phrasing per shape is what keeps a 30-prompt panel from
    reading like a mail merge; variant 0 is always the canonical wording.
    """
    noun = _maker_noun(topic)
    plural = _is_plural(topic)
    text = topic.text
    if category == "makers":
        return [
            f"Who are the leading {text} {noun} {ctx.location}?",
            f"Which {noun} are best known for {text} {ctx.location}?",
            f"Who makes the best {text} {ctx.location}?",
        ]
    if category == "comparison":
        first = (
            f"How do the top {ctx.industry} companies compare on {text}?"
            if ctx.industry
            else f"How do the top companies compare on {text}?"
        )
        return [
            first,
            f"How do the leading {text} {noun} compare?",
            f"What separates the top {text} {noun} from the rest?",
        ]
    if category == "alternatives":
        return [
            f"What are good alternatives to {ctx.competitor} for {text}?",
            f"Besides {ctx.competitor}, which {noun} should I look at for {text}?",
            f"Who competes with {ctx.competitor} in {text}?",
        ]
    if category == "best-of":
        return [
            f"Which companies are known for the best {text} {ctx.location}?",
            f"Which {noun} lead the market for {text} {ctx.location}?",
            f"What is the most trusted name in {text} {ctx.location}?",
        ]
    if category == "use-case":
        first = (
            f"Which {text} would you recommend and why?"
            if plural
            else f"Which {noun} would you recommend for {text}, and why?"
        )
        return [
            first,
            f"Which {noun} are the best choice for {text}?",
            f"If I need {text}, which companies should I evaluate?",
        ]
    return [  # recommendation
        (
            f"What are the best {text} available today?"
            if plural
            else f"What are the best {text} options available today?"
        ),
        f"Which {noun} should I consider first for {text}?",
        f"What are the most recommended {text} right now?",
    ]


def _question_specs(
    kyc, topics: list[Topic], count: int, brand_keys: list[str]
) -> list[PromptSpec]:
    """``count`` unique category-question prompts, cycling CATEGORIES/topics.

    Category advances by one per step while the topic advances by one per step
    *plus* one per completed lap of the six categories. Without that second
    stride the two indices move in lockstep whenever the topic count is a
    multiple of six, and a rich profile yields six questions where it should
    yield thirty-six. Alternate phrasings only start once every (category,
    topic) pair has been asked in its canonical wording.
    """
    ctx = _context(kyc)
    specs: list[PromptSpec] = []
    seen: set[str] = set()

    step = 0
    lap = len(CATEGORIES)
    cycle = lap * len(topics)  # one full pass over every (category, topic) pair
    max_steps = count * lap * len(topics) + count
    while len(specs) < count and step < max_steps:
        category = CATEGORIES[step % lap]
        topic = topics[(step + step // lap) % len(topics)]
        shapes = _shapes(category, topic, ctx)
        text = shapes[(step // cycle) % len(shapes)]
        step += 1
        if text in seen or _leaks_brand(text, brand_keys):
            continue
        seen.add(text)
        specs.append(PromptSpec(text=text, category=category))

    # Sparse KYC can run out of distinct templates: pad with natural variants
    # (still real English, still cycling categories).
    pad = 0
    max_pad = len(_PADDERS) * len(topics) + count
    while len(specs) < count and pad < max_pad:
        topic = topics[pad % len(topics)]
        text = _PADDERS[pad % len(_PADDERS)].format(topic=topic.text)
        pad += 1
        if text in seen or _leaks_brand(text, brand_keys):
            continue
        seen.add(text)
        category = CATEGORIES[len(specs) % lap]
        specs.append(PromptSpec(text=text, category=category))

    # Absolute last resort (single-topic sparse KYC, very high count): numbered
    # but still natural. Bounded, because the brand-leak filter can in principle
    # reject every candidate — a company literally named "Solutions" collides
    # with the neutral fallback topic. If that happens we return FEWER prompts
    # rather than a prompt set that scores the brand against itself; the runner
    # simply persists the shorter set.
    variant = 1
    max_variant = count * 4
    while len(specs) < count and variant <= max_variant:
        text = f"What are the best {topics[0].text} options worth considering ({variant})?"
        variant += 1
        if text in seen or _leaks_brand(text, brand_keys):
            continue
        seen.add(text)
        category = CATEGORIES[len(specs) % lap]
        specs.append(PromptSpec(text=text, category=category))

    return specs


def _brand_positions(budget: int, count: int) -> set[int]:
    """Spread ``budget`` brand-probe slots evenly across ``count`` positions."""
    if budget <= 0:
        return set()
    return {(i + 1) * count // (budget + 1) for i in range(budget)}


def generate_prompts(kyc, count: int) -> list[PromptSpec]:
    if count <= 0:
        return []

    company = clean_str(kyc.company, max_chars=120)
    brand_keys = _brand_keys(kyc)
    topics = _question_topics(kyc)
    products = _clean_list(kyc.products) if company else []

    # Brand probes are a minority: at most ~1/4 of prompts, never more than the
    # products we actually have.
    budget = min(len(products), count // 4)
    brand_positions = _brand_positions(budget, count)

    # More than enough unique category questions to fill every non-brand slot.
    questions = _question_specs(kyc, topics, count, brand_keys)

    specs: list[PromptSpec] = []
    seen: set[str] = set()
    q_index = 0
    p_index = 0

    for pos in range(count):
        spec: PromptSpec | None = None
        if pos in brand_positions and p_index < len(products):
            product = products[p_index]
            shape = _BRAND_PROBES[p_index % len(_BRAND_PROBES)]
            text = shape.format(product=product, company=company)
            p_index += 1
            if text not in seen:
                # Brand probes name the company on purpose — they are the one
                # exempt shape, and they are never scored as category questions.
                spec = PromptSpec(text=text, category=BRAND_PROBE)
        if spec is None:
            while q_index < len(questions) and questions[q_index].text in seen:
                q_index += 1
            if q_index >= len(questions):
                break
            spec = questions[q_index]
            q_index += 1
        seen.add(spec.text)
        specs.append(spec)

    return specs[:count]
