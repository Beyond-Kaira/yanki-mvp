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


def _response(prompt_id: str, engine: str, raw_text: str, footprint: bool) -> SimpleNamespace:
    return SimpleNamespace(
        prompt_id=prompt_id,
        engine=engine,
        raw_text=raw_text,
        footprint=footprint,
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


def test_landscape_does_not_repeat_own_term_as_a_competitor() -> None:
    prompts = [_prompt("p1", "recommendation"), _prompt("p2", "comparison")]
    responses = [
        _response("p1", "measured", "Yanki Demo Co operates in Turkey.", True),
        _response("p2", "measured", "Turkey also has Globex.", False),
    ]
    kyc = {**_KYC, "locations": ["Turkey"]}

    insights = summarize_insights(responses, prompts, kyc)

    assert insights is not None
    turkey = [
        entity
        for entity in insights.entityLandscape.entities
        if entity.name.casefold() == "turkey"
    ]
    assert len(turkey) == 1
    assert turkey[0].ownership == "shared"
    assert turkey[0].answers == 2
