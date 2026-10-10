"""Tests for the read-time visibility insights aggregation.

The design is docs/superpowers/specs/2026-08-04-visibility-insights-design.md.
Most assertions here are about the *denominator discipline* that spec rests on:
which answers count, which are withheld, and how a measured zero stays
distinguishable from something we never measured.

Fake prompt/response rows via ``SimpleNamespace`` — the same duck-typed
approach ``test_checker_summary.py`` uses, because the helper under test
imports no ORM.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.insights import summarize_insights

_KYC = {"company": "Yanki Demo Co", "aliases": ["Yanki Demo Co", "Yanki"]}

_NAMES_US = "I would recommend Yanki Demo Co here. Also worth a look: Globex."
_NAMES_RIVAL = "Two solid options are Globex and Initech."


def _prompt(prompt_id: str, category: str) -> SimpleNamespace:
    return SimpleNamespace(id=prompt_id, text=f"question {prompt_id}", category=category)


def _response(
    prompt_id: str,
    engine: str,
    raw_text: str,
    footprint: bool,
    audit: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        prompt_id=prompt_id,
        llm_provider="openrouter",
        model=engine,
        raw_text=raw_text,
        footprint=footprint,
        audit=audit,
    )


def test_brand_probe_answers_are_kept_out_of_the_scored_denominator() -> None:
    """A probe names the company in its own question, so its answer proves nothing.

    Two ordinary prompts and one brand-probe, each asked of two engines: six
    answers, of which four tested anything. Counting the probes would report a
    denominator of six and inflate every ratio built on it.
    """
    prompts = [
        _prompt("p1", "recommendation"),
        _prompt("p2", "makers"),
        _prompt("p3", "brand-probe"),
    ]
    responses = [
        _response("p1", "openai", _NAMES_US, True),
        _response("p1", "anthropic", _NAMES_RIVAL, False),
        _response("p2", "openai", _NAMES_RIVAL, False),
        _response("p2", "anthropic", _NAMES_RIVAL, False),
        _response("p3", "openai", _NAMES_US, True),
        _response("p3", "anthropic", _NAMES_US, True),
    ]

    insights = summarize_insights(responses, prompts, _KYC)

    assert insights is not None
    assert insights.scoredAnswers == 4
    assert insights.probe is not None
    assert (insights.probe.mentioned, insights.probe.total) == (2, 2)


def test_mention_share_uses_audit_pool_with_complete_name_matches() -> None:
    prompts = [_prompt("p1", "makers"), _prompt("p2", "best-of")]
    responses = [
        _response(
            "p1",
            "openai",
            "Amazon and eBay sell goods in Turkey. Turkish shoppers use both.",
            False,
            {"competitors": ["Amazon", "eBay", "Bay", "Turkey"]},
        ),
        _response(
            "p2",
            "openai",
            "Good options include eBay and Walmart in Turkey.",
            False,
            {"competitors": ["Walmart"]},
        ),
    ]

    insights = summarize_insights(responses, prompts, {**_KYC, "locations": ["Turkey"]})

    assert insights is not None
    competitors = {item.name: item.answers for item in insights.engines[0].competitors}
    assert competitors == {"eBay": 2, "Amazon": 1, "Walmart": 1}


def test_mention_share_does_not_guess_names_when_audit_pool_is_missing() -> None:
    insights = summarize_insights(
        [
            _response(
                "p1",
                "openai",
                "Good options in Turkey include eBay.",
                False,
                {"competitors": []},
            )
        ],
        [_prompt("p1", "makers")],
        {**_KYC, "locations": ["Turkey"]},
    )

    assert insights is not None
    assert insights.engines[0].competitors == []


def test_legacy_mention_share_uses_existing_name_heuristic() -> None:
    insights = summarize_insights(
        [_response("p1", "openai", "Acme and Globex are options.", False)],
        [_prompt("p1", "makers")],
        _KYC,
    )

    assert insights is not None
    assert {item.name for item in insights.engines[0].competitors} == {"Acme", "Globex"}


def test_entity_presence_requires_co_mention_with_the_brand() -> None:
    prompts = [_prompt("p1", "recommendation"), _prompt("p2", "comparison")]
    responses = [
        _response("p1", "measured", "Yanki Demo Co supports warehouse automation.", True),
        _response("p2", "measured", "Cobot platforms include Globex.", False),
    ]
    kyc = {**_KYC, "keywords": ["warehouse automation", "cobot", "safety scanner"]}

    insights = summarize_insights(responses, prompts, kyc)

    assert insights is not None
    entities = {entity.name: entity for entity in insights.entityCoverage.entities}
    assert entities["warehouse automation"].presence == "present"
    assert entities["cobot"].presence == "high-impact-missing"
    assert entities["safety scanner"].presence == "missing"


def test_profile_locations_are_context_entities_without_competitor_or_opportunity_labels() -> None:
    prompts = [_prompt("p1", "recommendation"), _prompt("p2", "comparison")]
    for location in ("Turkey", "United States"):
        responses = [
            _response(
                "p1",
                "measured",
                "Yanki Demo Co offers automation.",
                True,
                {"competitors": []},
            ),
            _response(
                "p2",
                "measured",
                f"{location} also has Globex.",
                False,
                {"competitors": ["Globex", location]},
            ),
        ]
        kyc = {**_KYC, "locations": [location], "competitors": ["Globex"]}

        insights = summarize_insights(responses, prompts, kyc)

        assert insights is not None
        assert location not in {entity.name for entity in insights.entityCoverage.entities}
        locations = [
            entity for entity in insights.entityLandscape.entities if entity.name == location
        ]
        assert len(locations) == 1
        assert locations[0].ownership == "location"
        assert locations[0].answers == 1
        assert [
            group.competitors for group in insights.gap.categories if group.category == "comparison"
        ] == [["Globex"]]


def test_landscape_filters_one_off_external_names_but_keeps_known_competitors() -> None:
    prompts = [
        _prompt("p1", "recommendation"),
        _prompt("p2", "comparison"),
        _prompt("p3", "makers"),
    ]
    responses = [
        _response("p1", "measured", "Globex and Paris are discussed.", False),
        _response("p2", "measured", "Globex is frequently recommended.", False),
        _response("p3", "measured", "Initech is another option.", False),
    ]
    kyc = {**_KYC, "competitors": ["Initech"]}

    insights = summarize_insights(responses, prompts, kyc)

    assert insights is not None
    names = {entity.name.casefold() for entity in insights.entityLandscape.entities}
    assert "globex" in names
    assert "initech" in names
    assert "paris" not in names
