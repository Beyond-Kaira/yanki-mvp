from __future__ import annotations

import math

import pytest

from app.pipeline.kyc import KYC, generate_kyc
from app.pipeline.prompts import BRAND_PROBE, CATEGORIES, generate_prompts
from app.providers.base import ProviderResult


@pytest.fixture
def defense_kyc() -> KYC:
    return KYC(
        company="Beyond Technologies",
        industry="Defense technology",
        products=["BAZNA FPV kamikaze drone", "Tayron UGV"],
        services=["ISR systems"],
        locations=["Türkiye"],
        competitors=["Baykar"],
    )


# The exact real prod KYC for https://beyondtech.com.tr (analysis 58913428),
# with locations left empty as the model returned them.
def _beyondtech_kyc(locations: list[str] | None = None) -> KYC:
    return KYC(
        company="Beyond Technologies",
        industry="Defense Technology, Unmanned Systems, Artificial Intelligence",
        description="A technology company specializing in autonomous systems.",
        aliases=["Beyond Technologies", "beyondtech"],
        products=[
            "BAZNA V7",
            "BAZNA V10",
            "BAZNA V15",
            "BAZNA F",
            "LIFTRON",
            "FEDAİ",
            "TAKTIK İKA",
            "TAKTIK OTONOMI SİSTEMİ — İKA",
            "GÖRÜNTÜ TABANLÜ SEYRÜSEFER SİSTEMİ — İHA",
        ],
        services=[
            "End-to-end development from concept to field integration",
            "Software development",
            "Hardware development",
            "System integration",
        ],
        keywords=[
            "unmanned aerial vehicle",
            "UAV",
            "unmanned ground vehicle",
            "UGV",
            "autonomous systems",
            "tactical kamikaze UAV",
            "fiber optic",
            "EW immune",
            "anti-armor",
            "RPG-7 capability",
            "payload capacity",
            "flight endurance",
            "artificial intelligence",
            "defense",
        ],
        locations=locations or [],
        competitors=[],
    )


class _CannedProvider:
    name = "canned"
    model = "canned"

    def __init__(self, text: str) -> None:
        self._text = text

    def generate(self, prompt: str) -> ProviderResult:
        return ProviderResult(text=self._text, model=self.model, cost_usd=0.0)


def test_generates_exactly_count(sample_kyc):
    specs = generate_prompts(sample_kyc, 10)
    assert len(specs) == 10


def test_every_prompt_has_text_and_category(sample_kyc):
    for spec in generate_prompts(sample_kyc, 10):
        assert spec.text.strip()
        assert spec.category in CATEGORIES or spec.category == BRAND_PROBE


def test_prompts_are_deduped(sample_kyc):
    texts = [spec.text for spec in generate_prompts(sample_kyc, 12)]
    assert len(texts) == len(set(texts))


def test_categories_are_cycled():
    # No products -> no brand probes -> the six category shapes cycle cleanly.
    kyc = KYC(company="Acme", keywords=["automation", "robotics", "logistics"])
    specs = generate_prompts(kyc, len(CATEGORIES))
    assert [spec.category for spec in specs] == CATEGORIES


def test_fills_from_sparse_kyc():
    sparse = KYC(company="Solo Co")
    specs = generate_prompts(sparse, 10)
    assert len(specs) == 10
    texts = [spec.text for spec in specs]
    assert len(texts) == len(set(texts))
    assert all(spec.text.strip() for spec in specs)


def test_zero_count_returns_empty(sample_kyc):
    assert generate_prompts(sample_kyc, 0) == []


def test_defense_fixture_reads_naturally(defense_kyc):
    specs = generate_prompts(defense_kyc, 10)
    texts = [spec.text for spec in specs]

    assert len(texts) == 10
    assert len(set(texts)) == 10
    # A specific product name surfaces.
    assert any("BAZNA" in text for text in texts)
    # The product-manufacturer-in-location shape is produced.
    assert any(
        text.startswith("Who are the leading ")
        and "manufacturers in Türkiye?" in text
        for text in texts
    )
    # None of the old broken mad-lib shapes.
    for text in texts:
        assert "best Information Technology available" not in text
        assert "best solutions in" not in text
        assert "providers for" not in text  # old "{industry} providers" phrasing


def test_defense_prompts_reference_products_and_services(defense_kyc):
    specs = generate_prompts(defense_kyc, 10)
    specific = ["BAZNA FPV kamikaze drone", "Tayron UGV", "ISR systems"]
    hits = sum(any(term in spec.text for term in specific) for spec in specs)
    assert hits >= math.ceil(10 / 3)


# --- Round 2: the exact real prod KYC (beyondtech.com.tr) -------------------

# Every product/model name; none of these may appear in a category slot.
_BEYONDTECH_PRODUCTS = [
    "BAZNA V7",
    "BAZNA V10",
    "BAZNA V15",
    "BAZNA F",
    "LIFTRON",
    "FEDAİ",
    "TAKTIK İKA",
    "TAKTIK OTONOMI SİSTEMİ — İKA",
    "GÖRÜNTÜ TABANLÜ SEYRÜSEFER SİSTEMİ — İHA",
]


def test_beyondtech_ten_unique_prompts():
    kyc = _beyondtech_kyc(locations=["Türkiye"])
    specs = generate_prompts(kyc, 10)
    texts = [spec.text for spec in specs]
    assert len(texts) == 10
    assert len(set(texts)) == 10


def test_beyondtech_no_product_in_category_slot():
    kyc = _beyondtech_kyc(locations=["Türkiye"])
    specs = generate_prompts(kyc, 10)
    for spec in specs:
        if spec.category == BRAND_PROBE:
            continue
        for product in _BEYONDTECH_PRODUCTS:
            assert product not in spec.text, spec.text
    # The specific broken shapes from the live run must not recur.
    for spec in specs:
        assert "BAZNA V10 manufacturers" not in spec.text
        assert "Which FEDAİ would you recommend" not in spec.text


def test_beyondtech_has_keyword_makers_question():
    kyc = _beyondtech_kyc(locations=["Türkiye"])
    texts = [spec.text for spec in generate_prompts(kyc, 10)]
    assert any(
        "manufacturers" in text
        and any(term in text for term in ("UAV", "unmanned", "kamikaze"))
        for text in texts
    )


def test_beyondtech_brand_probes_are_a_minority_and_well_formed():
    kyc = _beyondtech_kyc(locations=["Türkiye"])
    specs = generate_prompts(kyc, 10)
    probes = [spec for spec in specs if spec.category == BRAND_PROBE]
    assert 1 <= len(probes) <= 3
    for probe in probes:
        assert "Beyond Technologies" in probe.text
        assert any(product in probe.text for product in _BEYONDTECH_PRODUCTS)


def test_beyondtech_industry_uses_first_segment_only():
    kyc = _beyondtech_kyc(locations=["Türkiye"])
    texts = [spec.text for spec in generate_prompts(kyc, 10)]
    full_industry = "Defense Technology, Unmanned Systems, Artificial Intelligence"
    assert all(full_industry not in text for text in texts)
    # Where the industry surfaces it is the trimmed first segment.
    assert any("Defense Technology" in text for text in texts)


def test_beyondtech_cctld_fallback_feeds_location_into_prompts():
    # locations empty, but the .com.tr domain fallback yields Türkiye, so the
    # kyc function + generate_prompts together produce "in Türkiye" prompts.
    raw = _beyondtech_kyc(locations=[]).model_dump_json()
    kyc = generate_kyc("site text", "https://beyondtech.com.tr", _CannedProvider(raw))
    assert kyc.locations == ["Türkiye"]
    texts = [spec.text for spec in generate_prompts(kyc, 10)]
    assert any("in Türkiye" in text for text in texts)
    assert all("worldwide" not in text for text in texts)


# --- Workstream P: topic quality + invariants (pipeline-quality-plan.md) ----


# The spec attributes the real beyondtech KYC returned as "keywords". Every one
# of them produced a question no buyer has ever asked, at four paid calls each.
_SPEC_ATTRIBUTES = [
    "payload capacity",
    "flight endurance",
    "EW immune",
    "RPG-7 capability",
    "anti-armor",
]


def test_spec_attributes_never_become_questions():
    kyc = _beyondtech_kyc(locations=["Türkiye"])
    texts = [spec.text for spec in generate_prompts(kyc, 12)]
    for attribute in _SPEC_ATTRIBUTES:
        assert all(attribute not in text for text in texts), attribute


def test_category_is_the_first_topic_when_the_profile_has_one():
    # The field exists precisely so the category is not inferred from keywords.
    kyc = KYC(
        company="Globex",
        category="industrial robots",
        keywords=["automation", "logistics"],
    )
    first = generate_prompts(kyc, 1)[0]
    assert "industrial robots" in first.text


def test_use_cases_are_used_as_topics():
    kyc = KYC(company="Globex", use_cases=["warehouse automation"], keywords=[])
    texts = [spec.text for spec in generate_prompts(kyc, 6)]
    assert any("warehouse automation" in text for text in texts)


def test_a_brand_in_the_keywords_never_reaches_a_question():
    # SEO copy is full of the brand. Asking "What are the best Globex options?"
    # and then counting Globex in the answers is a self-fulfilling score.
    kyc = KYC(
        company="Globex Robotics",
        aliases=["Globex Robotics", "Globex", "globexrobotics"],
        keywords=["Globex Robotics", "globex robotics solutions", "warehouse robots"],
        competitors=["Globex Robotics Holding"],
    )
    specs = generate_prompts(kyc, 12)
    assert len(specs) == 12
    for spec in specs:
        if spec.category == BRAND_PROBE:
            continue
        assert "globex" not in spec.text.casefold(), spec.text


def test_brand_probes_may_still_name_the_company():
    # They are the one exempt shape: naming the product and the vendor is the
    # question, and they are tagged so scoring can tell them apart.
    kyc = KYC(
        company="Globex",
        keywords=["warehouse robots"],
        products=["PalletMover", "ArmBot"],
    )
    probes = [s for s in generate_prompts(kyc, 12) if s.category == BRAND_PROBE]
    assert probes
    assert all("Globex" in probe.text for probe in probes)


def test_six_topics_no_longer_collapse_to_six_questions():
    # Category and topic used to advance in lockstep, so a profile with exactly
    # six topics only ever produced six distinct questions before falling
    # through to the padders. All 36 pairs must be reachable.
    kyc = KYC(
        company="Globex",
        keywords=[
            "warehouse robots",
            "conveyor systems",
            "picking arms",
            "fleet software",
            "storage racks",
            "sorting machines",
        ],
    )
    specs = generate_prompts(kyc, 36)
    assert len(specs) == 36
    assert len({spec.text for spec in specs}) == 36
    # Every topic is actually asked about, not just the first few.
    for keyword in kyc.keywords:
        assert any(keyword in spec.text for spec in specs), keyword
    # And no padder was needed to get there.
    assert all("worth considering (" not in spec.text for spec in specs)


def test_maker_noun_matches_what_the_topic_is():
    goods = generate_prompts(KYC(company="A", keywords=["warehouse robots"]), 6)
    assert any("robots manufacturers" in spec.text for spec in goods)

    software = generate_prompts(KYC(company="B", category="CRM software"), 6)
    assert all("manufacturers" not in spec.text for spec in software)

    services = generate_prompts(KYC(company="C", services=["system integration"]), 6)
    assert any("providers" in spec.text for spec in services)


def test_placeholder_topics_never_reach_a_question():
    kyc = KYC(company="Globex", keywords=["N/A", "unknown"], category="robots")
    texts = [spec.text for spec in generate_prompts(kyc, 6)]
    assert all("N/A" not in text and "unknown" not in text for text in texts)


def test_sparse_profile_still_fills_the_panel():
    specs = generate_prompts(KYC(company="Solo Co"), 20)
    assert len(specs) == 20
    assert len({spec.text for spec in specs}) == 20


def test_phrasing_agrees_with_the_topic_number():
    plural = [s.text for s in generate_prompts(KYC(company="A", category="tactical UAVs"), 6)]
    assert "What are the best tactical UAVs available today?" in plural
    assert all("UAVs options" not in text for text in plural)

    singular = [
        s.text
        for s in generate_prompts(KYC(company="B", category="warehouse automation"), 6)
    ]
    assert "What are the best warehouse automation options available today?" in singular


def test_a_service_topic_is_not_asked_as_if_it_were_a_product():
    # "Which Software development would you recommend and why?" was the shape
    # this replaces.
    texts = [
        s.text for s in generate_prompts(KYC(company="A", services=["software development"]), 6)
    ]
    assert any(
        text == "Which providers would you recommend for software development, and why?"
        for text in texts
    )


# --------------------------------------------------------------------------
# Locations: a coverage claim is not a place (issue #18)
# --------------------------------------------------------------------------


def test_a_coverage_claim_is_skipped_for_the_real_place_behind_it(sample_kyc):
    """Measured on wise.com, whose profile led with a marketing number.

    ``locations`` came back ['160+ countries', 'United Kingdom', 'Estonia'].
    Taking [0] put "in 160+ countries" into three of ten *paid* questions.
    """
    from app.pipeline.prompts import primary_location

    kyc = sample_kyc.model_copy(
        update={"locations": ["160+ countries", "United Kingdom", "Estonia"]}
    )
    assert primary_location(kyc) == "United Kingdom"


@pytest.mark.parametrize(
    "junk",
    ["160+ countries", "40 currencies", "multiple countries", "global markets", "worldwide"],
)
def test_coverage_claims_never_count_as_places(sample_kyc, junk):
    from app.pipeline.prompts import primary_location

    kyc = sample_kyc.model_copy(update={"locations": [junk]})
    assert primary_location(kyc) == ""


def test_a_profile_with_only_coverage_claims_falls_back_to_worldwide(sample_kyc):
    kyc = sample_kyc.model_copy(update={"locations": ["160+ countries"], "category": "robots"})
    texts = " ".join(spec.text for spec in generate_prompts(kyc, 8))
    assert "160+" not in texts
    assert "worldwide" in texts


def test_real_places_still_reach_the_questions(sample_kyc):
    kyc = sample_kyc.model_copy(update={"locations": ["Berlin"], "category": "robots"})
    assert "in Berlin" in " ".join(spec.text for spec in generate_prompts(kyc, 8))


@pytest.mark.parametrize(
    ("place", "expected"),
    [
        ("Berlin", "Berlin"),
        ("Türkiye", "Türkiye"),
        ("United Kingdom", "the United Kingdom"),
        ("Netherlands", "the Netherlands"),
        ("USA", "the USA"),
    ],
)
def test_only_the_places_that_take_an_article_get_one(place, expected):
    """"in United Kingdom" is the kind of thing a reader clocks as machine-written."""
    from app.pipeline.prompts import location_phrase

    assert location_phrase(place) == expected
