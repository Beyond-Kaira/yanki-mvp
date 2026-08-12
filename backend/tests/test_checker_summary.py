"""Tests for the P5.3 read-time checker aggregation.

Two layers:

* **Unit** — the pure helper ``summarize_checker`` against mock-shaped answers
  (fake response rows via ``SimpleNamespace``): engine-presence grouping and
  sum-consistency, the proper-noun competitor heuristic, brand/alias exclusion,
  the sentence-starter stoplist, adjacent-token grouping (no fragment leakage),
  the top-N cap, and empty input.
* **API** — a DRY_RUN ``kind='checker'`` analysis, run end-to-end through the
  pipeline (all mocks, $0), then fetched via ``GET`` carries both fields; an MVP
  analysis carries ``null`` for both. Shares the in-memory SQLite fixtures with
  the rest of the API suite (``client`` and ``db_session`` see the same DB).
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.checker_summary import (
    TOP_N,
    CheckerSummary,
    summarize_checker,
)

# The exact shapes the DRY_RUN mock provider emits (see app/providers/mock.py).
_MENTION = (
    "For this I would recommend Yanki Demo Co. Other options in the market "
    "include Acme, Globex, Initech, Umbrella, Stark. (answer from the {eng} "
    "mock engine)"
)
_NO_MENTION = (
    "Some well-known options here include Acme, Globex, Initech, Umbrella, "
    "Stark. (answer from the {eng} mock engine)"
)
_MOCK_KYC = {"company": "Yanki Demo Co", "aliases": ["Yanki Demo Co", "Yanki"]}
_FILLERS = {"Acme", "Globex", "Initech", "Umbrella", "Stark"}


def _resp(engine: str, raw_text: str, footprint: bool | None) -> SimpleNamespace:
    return SimpleNamespace(engine=engine, raw_text=raw_text, footprint=footprint)


def _mock_responses() -> list[SimpleNamespace]:
    """12 responses across two engines; alternating mention / no-mention."""
    rows: list[SimpleNamespace] = []
    for engine in ("anthropic", "openai"):
        for i in range(6):
            hit = i % 2 == 0
            template = _MENTION if hit else _NO_MENTION
            rows.append(_resp(engine, template.format(eng=engine), hit))
    return rows


# --- engine_presence -----------------------------------------------------------


def test_engine_presence_groups_and_counts():
    summary = summarize_checker(_mock_responses(), _MOCK_KYC)
    by_engine = {e.engine: e for e in summary.engine_presence}
    assert set(by_engine) == {"anthropic", "openai"}
    # 6 responses per engine, 3 of them mentions (i in {0,2,4}).
    for stat in summary.engine_presence:
        assert stat.total == 6
        assert stat.mentioned == 3


def test_engine_presence_sum_consistent_with_totals():
    rows = _mock_responses()
    summary = summarize_checker(rows, _MOCK_KYC)
    hits = sum(1 for r in rows if r.footprint)
    assert sum(e.total for e in summary.engine_presence) == len(rows)
    assert sum(e.mentioned for e in summary.engine_presence) == hits


def test_engine_presence_footprint_none_is_not_a_mention():
    rows = [_resp("anthropic", _NO_MENTION.format(eng="anthropic"), None) for _ in range(3)]
    summary = summarize_checker(rows, _MOCK_KYC)
    (stat,) = summary.engine_presence
    assert stat.total == 3
    assert stat.mentioned == 0


def test_engine_presence_preserves_first_seen_order():
    # The map emits engines in first-seen (panel) order; pin it so a regression
    # that reorders or sorts the engines is caught.
    rows = [
        _resp("gemini", _NO_MENTION.format(eng="gemini"), False),
        _resp("anthropic", _NO_MENTION.format(eng="anthropic"), True),
        _resp("gemini", _MENTION.format(eng="gemini"), True),
        _resp("openai", _NO_MENTION.format(eng="openai"), False),
    ]
    summary = summarize_checker(rows, _MOCK_KYC)
    assert [e.engine for e in summary.engine_presence] == ["gemini", "anthropic", "openai"]


# --- competitors_appeared ------------------------------------------------------


def test_competitors_are_exactly_the_mock_fillers():
    summary = summarize_checker(_mock_responses(), _MOCK_KYC)
    names = {c.name for c in summary.competitors_appeared}
    assert names == _FILLERS
    # Every one of the 12 answers names every filler once.
    assert all(c.mentions == 12 for c in summary.competitors_appeared)


def test_searched_brand_and_aliases_excluded():
    summary = summarize_checker(_mock_responses(), _MOCK_KYC)
    names = {c.name.casefold() for c in summary.competitors_appeared}
    assert "yanki demo co" not in names
    assert "yanki" not in names
    assert not any("yanki" in n for n in names)


def test_exclusion_is_case_insensitive():
    rows = [_resp("anthropic", "I recommend YANKI DEMO CO and also Acme.", True)]
    summary = summarize_checker(rows, _MOCK_KYC)
    names = {c.name for c in summary.competitors_appeared}
    assert names == {"Acme"}


def test_adjacent_capitals_grouped_no_fragment_leak():
    # "Yanki Demo Co" must be excluded whole — no "Demo Co" / "Co" fragment.
    rows = [_resp("anthropic", "Yanki Demo Co. Acme is a strong pick.", True)]
    summary = summarize_checker(rows, _MOCK_KYC)
    names = {c.name for c in summary.competitors_appeared}
    assert names == {"Acme"}
    assert not any("Demo" in n or n == "Co" for n in names)


def test_sentence_starters_are_dropped():
    # "For", "Some", "Other" start sentences (capitalized) but are not brands.
    rows = [
        _resp("anthropic", "For this I recommend Acme. Some prefer Globex.", False),
        _resp("anthropic", "Other options include Initech.", False),
    ]
    summary = summarize_checker(rows, _MOCK_KYC)
    names = {c.name for c in summary.competitors_appeared}
    assert names == {"Acme", "Globex", "Initech"}
    assert not ({"For", "Some", "Other", "I", "This"} & names)


def test_leading_stopword_stripped_from_group():
    # "The Acme" -> "Acme" (leading stopword stripped), still excluding the brand.
    rows = [_resp("anthropic", "The Acme leads the market.", False)]
    summary = summarize_checker(rows, _MOCK_KYC)
    assert {c.name for c in summary.competitors_appeared} == {"Acme"}


def test_searched_brand_possessive_form_is_excluded():
    # An answer about the brand written in the possessive ("Nike's ...") must not
    # surface the brand as its own competitor.
    kyc = {"company": "Nike", "aliases": ["Nike"]}
    rows = [_resp("anthropic", "Nike's new line beats Adidas.", True)]
    summary = summarize_checker(rows, kyc)
    names = {c.name for c in summary.competitors_appeared}
    assert names == {"Adidas"}
    assert not any("nike" in n.casefold() for n in names)


def test_competitor_possessive_keeps_its_name():
    # A competitor that genuinely ends in "'s" keeps its name (only the exclusion
    # comparison strips the possessive, not the reported name).
    rows = [_resp("anthropic", "McDonald's beats Acme.", False)]
    summary = summarize_checker(rows, _MOCK_KYC)
    assert {c.name for c in summary.competitors_appeared} == {"McDonald's", "Acme"}


def test_recommendation_verb_stripped_from_group():
    # "Try Acme" / "Choose Globex" -> the verb is stripped, the brand survives.
    rows = [_resp("anthropic", "Try Acme today. Choose Globex over Initech.", False)]
    summary = summarize_checker(rows, _MOCK_KYC)
    names = {c.name for c in summary.competitors_appeared}
    assert names == {"Acme", "Globex", "Initech"}
    assert not ({"Try", "Choose"} & names)


def test_verb_welded_brand_still_excluded():
    # "Choose Nike" -> strip "Choose" -> "Nike" -> excluded as the searched brand.
    kyc = {"company": "Nike", "aliases": ["Nike"]}
    rows = [_resp("anthropic", "Choose Nike over Adidas.", True)]
    summary = summarize_checker(rows, kyc)
    assert {c.name for c in summary.competitors_appeared} == {"Adidas"}


def test_ambiguous_leading_particle_kept_in_multiword_name():
    # Short TR function words that begin English brands ("De Beers", "Ben
    # Sherman") keep their first token — no "Beers" / "Sherman" fragment.
    rows = [_resp("anthropic", "The best pick is De Beers, then Ben Sherman.", False)]
    summary = summarize_checker(rows, _MOCK_KYC)
    names = {c.name for c in summary.competitors_appeared}
    assert {"De Beers", "Ben Sherman"} <= names
    assert "Beers" not in names
    assert "Sherman" not in names


def test_standalone_ambiguous_particle_still_dropped():
    # The same particles are still dropped when they stand alone (bare TR lead).
    rows = [_resp("anthropic", "De also. Ben too. Acme leads.", False)]
    summary = summarize_checker(rows, _MOCK_KYC)
    assert {c.name for c in summary.competitors_appeared} == {"Acme"}


def test_mentions_counted_once_per_answer():
    # A brand repeated within one answer counts once for that answer.
    rows = [
        _resp("anthropic", "Acme and Acme again. Also Globex.", False),
        _resp("openai", "Acme only here.", False),
    ]
    summary = summarize_checker(rows, _MOCK_KYC)
    by_name = {c.name: c.mentions for c in summary.competitors_appeared}
    assert by_name == {"Acme": 2, "Globex": 1}


def test_ranked_by_mention_count_desc_then_name():
    rows = [
        _resp("anthropic", "Zeta and Acme.", False),
        _resp("anthropic", "Acme wins.", False),
        _resp("anthropic", "Acme again.", False),
        _resp("anthropic", "Zeta once more.", False),
    ]
    summary = summarize_checker(rows, _MOCK_KYC)
    ranked = [(c.name, c.mentions) for c in summary.competitors_appeared]
    # Acme(3) before Zeta(2); count-desc ordering.
    assert ranked == [("Acme", 3), ("Zeta", 2)]


def test_top_n_cap():
    # 15 distinct one-mention brands -> only TOP_N returned, alphabetically.
    names = [f"Brand{chr(ord('A') + i)}" for i in range(15)]
    rows = [_resp("anthropic", f"{name} is good.", False) for name in names]
    summary = summarize_checker(rows, _MOCK_KYC)
    assert len(summary.competitors_appeared) == TOP_N
    returned = [c.name for c in summary.competitors_appeared]
    assert returned == sorted(names)[:TOP_N]


def test_no_kyc_excludes_nothing():
    # Without kyc there are no exclusions, so the brand surfaces too.
    rows = [_resp("anthropic", "Yanki Demo Co and Acme both appear.", True)]
    summary = summarize_checker(rows, None)
    names = {c.name for c in summary.competitors_appeared}
    assert names == {"Yanki Demo Co", "Acme"}


def test_empty_responses_returns_empty_summary():
    summary = summarize_checker([], _MOCK_KYC)
    assert isinstance(summary, CheckerSummary)
    assert summary.engine_presence == []
    assert summary.competitors_appeared == []


# --- API level -----------------------------------------------------------------


def _dry_run_settings() -> SimpleNamespace:
    return SimpleNamespace(
        dry_run=True,
        panel_engines="anthropic,openai,gemini,perplexity",
        prompt_count=10,
        max_responses_per_job=60,
        anthropic_api_key="",
        openai_api_key="",
    )


def test_checker_get_carries_presence_and_competitors(client, db_session):
    from app.db.models import Analysis
    from app.pipeline import runner

    analysis = Analysis(
        url="checker://nike/running shoes",
        status="running",
        kind="checker",
        brand="nike",
        category="running shoes",
        lang="en",
    )
    db_session.add(analysis)
    db_session.commit()

    runner.run_pipeline(db_session, analysis.id, _dry_run_settings())

    geo = client.get(f"/api/v1/analyses/{analysis.id}/geo").json()

    presence = geo["engine_presence"]
    assert presence is not None
    # Measured path: one engine entry; totals match total_responses.
    assert len(presence) == 1
    assert presence[0]["engine"] == "measured"
    assert sum(e["total"] for e in presence) == geo["total_responses"] == 12
    assert sum(e["mentioned"] for e in presence) == geo["footprint_count"]

    competitors = geo["competitors_appeared"]
    assert competitors is not None
    # Measured mock answers name Acme/Globex; brand itself is excluded.
    names = {c["name"] for c in competitors}
    assert "Acme" in names or "Globex" in names
    assert not any("yanki" in c["name"].casefold() for c in competitors)
    assert isinstance(geo.get("interventions"), list)


def test_mvp_get_has_null_checker_fields(client, signed_in):
    signed_in(email="mvp-summary@example.test")
    resp = client.post("/api/v1/analyses", json={"url": "https://acme.test"})
    assert resp.status_code == 202, resp.text
    analysis_id = resp.json()["id"]
    geo = client.get(f"/api/v1/analyses/{analysis_id}/geo").json()
    assert geo["engine_presence"] is None
    assert geo["competitors_appeared"] is None
