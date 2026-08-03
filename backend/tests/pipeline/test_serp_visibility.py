"""SERP visibility: query building, hit detection, scoring, and the run pass."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.pipeline.kyc import KYC
from app.pipeline.serp_visibility import (
    STATUS_NO_TOPICS,
    STATUS_OK,
    STATUS_UNAVAILABLE,
    VIA_DOMAIN,
    VIA_TEXT,
    build_queries,
    detect,
    run_serp,
    serp_score,
    site_hosts,
)
from app.serp.base import SerpPage, SerpResult, SerpUnavailable


def _page(*results: SerpResult, query: str = "q", unresponsive: tuple[str, ...] = ()) -> SerpPage:
    return SerpPage(query=query, results=results, unresponsive_engines=unresponsive)


def _result(rank: int, url: str, title: str = "", content: str = "") -> SerpResult:
    return SerpResult(rank=rank, url=url, title=title, content=content, engine="test")


class _FakeSource:
    """A scripted source: one page (or exception) per query, in order."""

    name = "fake"

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.queries: list[str] = []

    def search(self, query: str) -> SerpPage:
        self.queries.append(query)
        outcome = self._outcomes.pop(0) if self._outcomes else _page()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


# --------------------------------------------------------------------------
# build_queries
# --------------------------------------------------------------------------


def test_the_buying_category_leads_the_queries(sample_kyc):
    """``topic_pool`` orders by confidence, so the category is queried first.

    Later queries rotate onto the other topics on purpose — the same coverage
    rotation prompt generation uses — so this pins the ordering, not exclusivity.
    """
    kyc = sample_kyc.model_copy(update={"category": "warehouse robots"})
    queries = build_queries(kyc, 4)
    assert len(queries) == 4
    assert "warehouse robots" in queries[0]


def test_queries_never_name_the_brand(sample_kyc):
    """The invariant ADR-27 set for prompts, on the other surface.

    A brand in the keywords is ordinary SEO copy, and searching for the brand
    and then counting the brand would score it against itself.
    """
    kyc = sample_kyc.model_copy(
        update={"category": "", "keywords": ["Acme Robotics", "acme", "warehouse robots"]}
    )
    queries = build_queries(kyc, 6)
    assert queries
    for query in queries:
        assert "acme" not in query.casefold()


def test_queries_are_distinct(sample_kyc):
    kyc = sample_kyc.model_copy(update={"category": "warehouse robots"})
    queries = build_queries(kyc, 8)
    assert len(queries) == len(set(queries))


def test_queries_are_deterministic(sample_kyc):
    assert build_queries(sample_kyc, 6) == build_queries(sample_kyc, 6)


def test_a_known_location_adds_a_locally_qualified_query(sample_kyc):
    kyc = sample_kyc.model_copy(update={"category": "warehouse robots", "locations": ["Berlin"]})
    assert any("in Berlin" in q for q in build_queries(kyc, 4))


def test_no_location_produces_no_dangling_qualifier(sample_kyc):
    kyc = sample_kyc.model_copy(update={"category": "warehouse robots", "locations": []})
    queries = build_queries(kyc, 6)
    assert queries
    assert all(" in " not in q for q in queries)


def test_a_profile_with_no_category_like_topic_yields_nothing():
    """Refuse to invent a query rather than search for "solutions"."""
    kyc = KYC(company="Acme", aliases=["Acme"], keywords=[], services=[], industry="")
    assert build_queries(kyc, 6) == []


def test_a_non_positive_count_yields_nothing(sample_kyc):
    assert build_queries(sample_kyc, 0) == []


def test_topics_and_shapes_rotate_rather_than_moving_in_lockstep(sample_kyc):
    """Six topics must not collapse to six queries (the prompts.py lesson)."""
    kyc = sample_kyc.model_copy(
        update={
            "category": "",
            "use_cases": [],
            "keywords": ["robots", "conveyors", "sorters", "pickers", "palletisers", "agvs"],
            "services": [],
            "industry": "",
            "locations": [],
        }
    )
    queries = build_queries(kyc, 12)
    assert len(queries) == 12
    assert len({q.split()[-1] for q in queries}) > 1


# --------------------------------------------------------------------------
# detection
# --------------------------------------------------------------------------


def test_the_companys_own_site_is_a_domain_hit(sample_kyc):
    hosts = site_hosts("https://acmerobotics.example/")
    page = _page(_result(1, "https://acmerobotics.example/products", title="Products"))
    hit = detect(page, sample_kyc, hosts)
    assert hit is not None
    assert hit.via == VIA_DOMAIN
    assert hit.rank == 1


def test_www_and_subdomains_count_as_the_same_site(sample_kyc):
    hosts = site_hosts("https://www.acmerobotics.example/")
    for url in ("https://acmerobotics.example/", "https://shop.acmerobotics.example/x"):
        assert detect(_page(_result(1, url)), sample_kyc, hosts) is not None


def test_a_lookalike_domain_is_not_the_companys_site(sample_kyc):
    hosts = site_hosts("https://acmerobotics.example/")
    page = _page(_result(1, "https://notacmerobotics.example/"))
    assert detect(page, sample_kyc, hosts) is None


def test_someone_elses_page_naming_the_company_is_a_text_hit(sample_kyc):
    page = _page(
        _result(1, "https://reviews.example/top", title="Top 10", content="We rate Acme Robotics.")
    )
    hit = detect(page, sample_kyc, frozenset())
    assert hit is not None
    assert hit.via == VIA_TEXT
    assert "Acme Robotics" in hit.snippet


def test_the_first_appearance_wins_so_the_rank_is_the_best_one(sample_kyc):
    hosts = site_hosts("https://acmerobotics.example/")
    page = _page(
        _result(1, "https://other.example/", title="Nothing relevant"),
        _result(2, "https://reviews.example/", content="Acme Robotics is solid."),
        _result(3, "https://acmerobotics.example/"),
    )
    hit = detect(page, sample_kyc, hosts)
    assert hit is not None
    assert hit.rank == 2
    assert hit.via == VIA_TEXT


def test_an_absent_company_is_no_hit(sample_kyc):
    page = _page(_result(1, "https://globex.example/", title="Globex", content="Globex robots."))
    assert detect(page, sample_kyc, frozenset()) is None


def test_a_checker_run_has_no_site_of_its_own():
    """We were handed a brand, not a domain — claiming one would be a guess."""
    assert site_hosts("checker://acme/robots") == frozenset()
    assert site_hosts("") == frozenset()


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------


def test_score_is_hits_over_measured():
    assert serp_score(3, 6) == 0.5


def test_score_is_none_when_nothing_could_be_measured():
    """Not 0.0 — the two say opposite things to a customer."""
    assert serp_score(0, 0) is None


# --------------------------------------------------------------------------
# run_serp
# --------------------------------------------------------------------------


@pytest.fixture
def serp_settings():
    return SimpleNamespace(serp_query_count=3)


@pytest.fixture
def analysis(db_session, models):
    row = models.Analysis(url="https://acmerobotics.example", status="running")
    db_session.add(row)
    db_session.flush()
    return row


def _checks(db_session, models, analysis):
    from sqlalchemy import select

    return list(
        db_session.execute(
            select(models.SerpCheck).where(models.SerpCheck.analysis_id == analysis.id)
        )
        .scalars()
        .all()
    )


def test_a_clean_run_scores_and_records_every_query(
    db_session, models, analysis, sample_kyc, serp_settings
):
    kyc = sample_kyc.model_copy(update={"category": "warehouse robots"})
    source = _FakeSource(
        [
            _page(_result(1, "https://acmerobotics.example/")),
            _page(_result(1, "https://globex.example/")),
            _page(_result(1, "https://reviews.example/", content="Acme Robotics wins.")),
        ]
    )

    outcome = run_serp(db_session, analysis, kyc, source, serp_settings)

    assert outcome.status == STATUS_OK
    assert (outcome.hits, outcome.queries) == (2, 3)
    assert outcome.score == pytest.approx(2 / 3)
    rows = _checks(db_session, models, analysis)
    assert len(rows) == 3
    assert sorted(bool(r.hit) for r in rows) == [False, True, True]
    assert {r.source for r in rows} == {"fake"}


def test_an_unreadable_page_is_dropped_from_the_denominator_not_counted_as_a_miss(
    db_session, models, analysis, sample_kyc, serp_settings
):
    """The heart of the honesty rule.

    Two of three queries came back with every engine blocked. The score is
    1 hit / 1 readable page, not 1/3 — we did not look at the other two.
    """
    kyc = sample_kyc.model_copy(update={"category": "warehouse robots"})
    source = _FakeSource(
        [
            _page(_result(1, "https://acmerobotics.example/")),
            _page(unresponsive=("brave", "duckduckgo")),
            _page(unresponsive=("brave",)),
        ]
    )

    outcome = run_serp(db_session, analysis, kyc, source, serp_settings)

    assert (outcome.hits, outcome.queries) == (1, 1)
    assert outcome.score == 1.0
    rows = _checks(db_session, models, analysis)
    assert len(rows) == 3
    assert sum(1 for r in rows if r.hit is None) == 2
    unreadable = next(r for r in rows if r.hit is None)
    assert unreadable.unresponsive_engines


def test_an_unreachable_instance_records_the_gap_and_reports_not_measured(
    db_session, models, analysis, sample_kyc, serp_settings
):
    kyc = sample_kyc.model_copy(update={"category": "warehouse robots"})
    source = _FakeSource([SerpUnavailable("refused")] * 3)

    outcome = run_serp(db_session, analysis, kyc, source, serp_settings)

    assert outcome.status == STATUS_UNAVAILABLE
    assert outcome.score is None
    assert len(_checks(db_session, models, analysis)) == 3


def test_one_flaky_query_does_not_lose_the_others(
    db_session, models, analysis, sample_kyc, serp_settings
):
    kyc = sample_kyc.model_copy(update={"category": "warehouse robots"})
    source = _FakeSource(
        [
            SerpUnavailable("timeout"),
            _page(_result(1, "https://acmerobotics.example/")),
            _page(_result(1, "https://globex.example/")),
        ]
    )

    outcome = run_serp(db_session, analysis, kyc, source, serp_settings)

    assert outcome.status == STATUS_OK
    assert (outcome.hits, outcome.queries) == (1, 2)


def test_a_profile_with_nothing_searchable_reports_no_topics(
    db_session, models, analysis, serp_settings
):
    kyc = KYC(company="Acme", aliases=["Acme"])
    source = _FakeSource([])

    outcome = run_serp(db_session, analysis, kyc, source, serp_settings)

    assert outcome.status == STATUS_NO_TOPICS
    assert outcome.score is None
    assert source.queries == []
    assert _checks(db_session, models, analysis) == []


def test_a_hit_records_the_evidence_behind_it(
    db_session, models, analysis, sample_kyc, serp_settings
):
    kyc = sample_kyc.model_copy(update={"category": "warehouse robots"})
    source = _FakeSource(
        [_page(_result(2, "https://acmerobotics.example/x", title="Acme Robotics — Home"))]
    )
    source._outcomes = [source._outcomes[0]] + [_page(), _page()]

    run_serp(db_session, analysis, kyc, source, serp_settings)

    row = next(r for r in _checks(db_session, models, analysis) if r.hit)
    assert row.rank == 2
    assert row.matched_url == "https://acmerobotics.example/x"
    assert row.matched_via == VIA_DOMAIN
    assert row.matched_snippet
    assert row.query


def test_a_source_that_raises_anything_at_all_still_cannot_fail_the_run(
    db_session, models, analysis, sample_kyc, serp_settings
):
    """Fail-open in the strong sense: not just the failure we anticipated.

    An adapter bug (AttributeError, ValueError, anything) must cost the run its
    SERP number and nothing else — the analysis has already paid for a crawl, a
    KYC call and the whole LLM panel by the time this runs.
    """
    kyc = sample_kyc.model_copy(update={"category": "warehouse robots"})

    class _BuggySource:
        name = "buggy"

        def search(self, query):
            raise AttributeError("a defect in the adapter, not an outage")

    outcome = run_serp(db_session, analysis, kyc, _BuggySource(), serp_settings)

    assert outcome.status == STATUS_UNAVAILABLE
    assert outcome.score is None
    # Still recorded, so the gap is visible rather than looking like queries we
    # never ran.
    assert len(_checks(db_session, models, analysis)) == 3
