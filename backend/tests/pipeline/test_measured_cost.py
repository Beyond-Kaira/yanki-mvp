"""Cost accounting on the measured/simulated GEO path.

The pipeline priced every provider call it made and then threw the number away:
``execute_measured`` wrote a literal ``Decimal("0")`` into ``responses.cost_usd``
for every row. Because ``CHECKER_DAILY_USD_CAP`` is enforced by summing exactly
that column, the cap could never trip on the live default path — and the credit
ledger M1 plans to seed from that column would have been seeded with zeros.

These tests pin the invariant the fix establishes: **a paid call is a recorded
call.** Each stage reports its own price, the audit sums them, and the row
stores the total.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.pipeline.execute_measured import _record_cost, run_measured_execute
from app.pipeline.measured import run_measured_audit
from app.pipeline.simulated import run_simulated_audit
from app.providers.base import ProviderResult
from app.providers.tavily import DEFAULT_SEARCH_PRICE_USD, TavilyClient


class _StubLLM:
    """An LLM that returns canned JSON and a known price per call."""

    model = "stub/model"

    def __init__(self, payloads: list[str], cost_per_call: float) -> None:
        self._payloads = list(payloads)
        self._cost = cost_per_call
        self.calls = 0

    def chat(self, messages, **kwargs) -> ProviderResult:
        self.calls += 1
        text = self._payloads.pop(0) if self._payloads else "{}"
        return ProviderResult(text=text, model=self.model, cost_usd=self._cost)


class _StubSearch:
    """A search client priced like the real one, without the network."""

    def __init__(self, price: float) -> None:
        self._price = price

    def search(self, query: str, *, max_results: int = 5):
        return {
            "query": query,
            "result_count": 1,
            "results": [
                {
                    "rank": 1,
                    "title": "Acme overview",
                    "url": "https://acme.example/about",
                    "snippet": "Acme is recommended.",
                    "domain": "acme.example",
                    "relevance_score": 0.9,
                    "brands_mentioned": ["Acme"],
                }
            ],
            "search_mode": "tavily_live",
            "search_provider": "tavily",
            "searched_at": "2026-08-05T00:00:00+00:00",
            "_cost_usd": self._price,
        }


_GROUNDED_JSON = (
    '{"grounded_answer": "Acme is a strong option [1].", '
    '"citations": [{"result_rank": 1, "url": "https://acme.example/about"}], '
    '"competitors": [], "answer_summary": "ok"}'
)
_AUDIT_JSON = (
    '{"intent": "informational", "mention_context": "primary_recommendation", '
    '"recommendation_reasoning": "r", "reasoning_trace": {}, '
    '"visibility_drivers": {}, "visibility_gaps": {}, "trust_signals": [], '
    '"entities_associated_with_brand": [], "sentiment": "positive", '
    '"content_improvement_opportunities": []}'
)


def test_dry_run_audits_report_zero_cost_explicitly():
    """DRY_RUN must be $0 — and must SAY so, not merely omit the field."""

    measured = run_measured_audit(
        brand="Yanki Demo Co",
        prompt="Best analytics tools",
        prompt_group="recommendation",
        owned_domains=["yankidemoco.example"],
        dry_run=True,
    )
    simulated = run_simulated_audit(
        brand="Yanki Demo Co",
        prompt="Best analytics tools",
        prompt_group="recommendation",
        owned_domains=["yankidemoco.example"],
        dry_run=True,
    )

    assert measured["_cost_usd"] == 0.0
    assert simulated["_cost_usd"] == 0.0


def test_measured_audit_sums_search_and_both_llm_calls():
    llm = _StubLLM([_GROUNDED_JSON, _AUDIT_JSON], cost_per_call=0.002)
    search = _StubSearch(price=0.008)

    record = run_measured_audit(
        brand="Acme",
        prompt="Best widgets",
        prompt_group="recommendation",
        owned_domains=["acme.example"],
        llm=llm,
        search=search,
        dry_run=False,
    )

    assert llm.calls == 2, "grounded answer + audit extraction"
    # 0.008 search + 0.002 grounded + 0.002 audit
    assert record["_cost_usd"] == 0.012


def test_a_failed_llm_call_still_reports_the_search_it_already_paid_for():
    """The search is billed on return, whatever happens next."""

    class _ExplodingLLM:
        model = "stub/model"

        def chat(self, messages, **kwargs):
            raise RuntimeError("upstream 500")

    record = run_measured_audit(
        brand="Acme",
        prompt="Best widgets",
        prompt_group="recommendation",
        owned_domains=["acme.example"],
        llm=_ExplodingLLM(),
        search=_StubSearch(price=0.008),
        dry_run=False,
    )

    assert record["error"] is True
    assert record["_cost_usd"] == 0.008


def test_simulated_audit_reports_its_single_call():
    llm = _StubLLM(['{"simulated_answer": "Acme leads.", "citations": []}'], cost_per_call=0.003)

    record = run_simulated_audit(
        brand="Acme",
        prompt="Best widgets",
        prompt_group="recommendation",
        owned_domains=["acme.example"],
        llm=llm,
        dry_run=False,
    )

    assert record["_cost_usd"] == 0.003


def test_tavily_client_prices_every_search_and_the_mock_prices_none():
    client = TavilyClient(api_key="k", search_price_usd=0.02)
    assert client._search_price_usd == 0.02
    assert DEFAULT_SEARCH_PRICE_USD > 0, "a $0 default would silently disarm the cap"


def test_record_cost_is_defensive_about_junk():
    assert _record_cost({}) == Decimal("0")
    assert _record_cost({"_cost_usd": None}) == Decimal("0")
    assert _record_cost({"_cost_usd": "not-a-number"}) == Decimal("0")
    # A vendor reporting a negative must not buy back already-spent budget.
    assert _record_cost({"_cost_usd": -5}) == Decimal("0")
    # Quantized to the Numeric(10,6) the column declares.
    assert _record_cost({"_cost_usd": 0.0123456789}) == Decimal("0.012346")


def test_execute_persists_the_cost_onto_every_response_row(db_session, make_analysis):
    analysis = make_analysis(url="https://acme.example", kyc={"company": "Acme"})
    prompts = []
    for index in range(2):
        from app.db.models import Prompt

        prompt = Prompt(
            analysis_id=analysis.id,
            text=f"Best widgets {index}",
            category="recommendation",
        )
        db_session.add(prompt)
        prompts.append(prompt)
    db_session.commit()

    settings = SimpleNamespace(
        dry_run=True,
        geo_mode="measured",
        max_responses_per_job=60,
        openrouter_model="stub/model",
    )

    rows = run_measured_execute(db_session, analysis, prompts, settings)
    db_session.commit()

    assert len(rows) == 2
    # DRY_RUN spends nothing, and the column now carries that as a recorded fact.
    assert all(row.cost_usd == Decimal("0") for row in rows)
    assert all(isinstance(row.cost_usd, Decimal) for row in rows)
