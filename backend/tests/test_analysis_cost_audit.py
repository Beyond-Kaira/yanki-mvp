"""Per-model analysis spend reaches the immutable terminal audit event."""

from decimal import Decimal

from sqlalchemy import select

from app.db.models import Analysis, AuditEvent, Prompt, Response
from app.services.analyses import cost_breakdown, spend_on
from app.worker import _record_terminal_event


def _response(db_session, analysis, prompt, engine, model, cost):
    db_session.add(
        Response(
            analysis_id=analysis.id,
            prompt_id=prompt.id,
            engine=engine,
            model=model,
            raw_text="answer",
            cost_usd=Decimal(cost),
        )
    )


def test_cost_breakdown_groups_questions_and_usd_by_provider_model(db_session):
    analysis = Analysis(
        url="https://acme.test",
        status="done",
        kyc_cost_usd=Decimal("0.001000"),
        kyc_usage=[
            {
                "provider": "openrouter",
                "model": "openai/gpt-4o-mini",
                "stage": "kyc",
                "cost_usd": "0.001000",
            }
        ],
    )
    db_session.add(analysis)
    db_session.flush()
    prompts = [
        Prompt(analysis_id=analysis.id, text=f"question {index}", category="discovery")
        for index in range(2)
    ]
    db_session.add_all(prompts)
    db_session.flush()

    _response(db_session, analysis, prompts[0], "gemini", "gemini-flash-lite", "0.002000")
    _response(db_session, analysis, prompts[1], "gemini", "gemini-flash-lite", "0.003000")
    _response(db_session, analysis, prompts[0], "perplexity", "sonar", "0.004000")
    _response(db_session, analysis, prompts[1], "perplexity", "sonar", "0.005000")
    db_session.commit()

    detail = cost_breakdown(db_session, analysis)

    assert detail["total_usd"] == "0.015000"
    assert detail["question_count"] == 2
    assert detail["response_count"] == 4
    by_provider = {item["provider"]: item for item in detail["providers"]}
    assert by_provider["gemini"] == {
        "provider": "gemini",
        "model": "gemini-flash-lite",
        "stages": ["answers"],
        "question_count": 2,
        "operation_count": 2,
        "cost_usd": "0.005000",
    }
    assert by_provider["perplexity"]["cost_usd"] == "0.009000"
    assert by_provider["openrouter"]["stages"] == ["kyc"]
    assert spend_on(db_session, analysis.id) == Decimal("0.015000")


def test_terminal_event_keeps_cost_detail_after_the_analysis_finishes(db_session):
    analysis = Analysis(url="https://acme.test", status="done")
    db_session.add(analysis)
    db_session.flush()
    prompt = Prompt(analysis_id=analysis.id, text="best widgets", category="recommendation")
    db_session.add(prompt)
    db_session.flush()
    _response(db_session, analysis, prompt, "perplexity", "sonar", "0.004200")
    db_session.commit()

    _record_terminal_event(db_session, analysis)

    event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.action == "analysis:complete")
    )
    assert event is not None
    assert event.entity_id == analysis.id
    assert event.after["url"] == "https://acme.test"
    assert event.detail["cost"]["total_usd"] == "0.004200"
    assert event.detail["cost"]["providers"][0]["provider"] == "perplexity"
    assert event.record_hash is not None
