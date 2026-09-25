"""Authenticated global GEO rankings and the retained question-generation API."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.org_dependencies import requires
from app.config import Settings, get_settings
from app.db.models import Organization, UsageCounter
from app.db.session import get_session
from app.industry_citations.questions import (
    IndustryQuestionRequest,
    IndustryQuestionResponse,
    generate_questions,
)
from app.industry_citations.ranking import (
    IndustryRankingPage,
    IndustrySector,
    build_industry_ranking,
    list_industry_sectors,
)
from app.providers.registry import get_measured_llm
from app.services import audit
from app.services.permissions import ANALYSIS_READ, ANALYSIS_RUN
from app.services.tenancy import OrgContext

router = APIRouter(prefix="/api/v1/industry-citations", tags=["industry-citations"])
QUESTION_REQUESTS_PER_HOUR = 10


@router.get("/sectors", response_model=list[IndustrySector])
def sectors(
    _org: Annotated[OrgContext, Depends(requires(ANALYSIS_READ))],
    session: Annotated[Session, Depends(get_session)],
) -> list[IndustrySector]:
    # Explicitly global aggregates; no tenant-owned record details are returned.
    return list_industry_sectors(session)


@router.get("/ranking", response_model=IndustryRankingPage)
def ranking(
    _org: Annotated[OrgContext, Depends(requires(ANALYSIS_READ))],
    session: Annotated[Session, Depends(get_session)],
    sector: Annotated[str, Query(min_length=1, max_length=200)],
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> IndustryRankingPage:
    try:
        report = build_industry_ranking(session, sector)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    selected = [
        site.model_copy(update={"pages": site.pages[:50]})
        for site in report.sites[offset : offset + limit]
    ]
    return IndustryRankingPage(
        **report.model_dump(exclude={"sites"}),
        sites=selected,
        offset=offset,
        limit=limit,
    )


def reserve_generation(session: Session, org: OrgContext) -> None:
    """Persist attempts before provider spend; Postgres org lock serializes writers."""
    now = datetime.now(UTC)
    window = now.replace(minute=0, second=0, microsecond=0)
    session.execute(select(Organization).where(Organization.id == org.org_id).with_for_update())
    counter = session.scalar(
        select(UsageCounter).where(
            UsageCounter.org_id == org.org_id,
            UsageCounter.metric == "industry_questions",
            UsageCounter.window_start == window,
        )
    )
    if counter is not None and counter.used >= QUESTION_REQUESTS_PER_HOUR:
        session.rollback()
        retry_after = max(1, int((window + timedelta(hours=1) - now).total_seconds()))
        raise HTTPException(
            429,
            "Question generation limit reached. Try again next hour.",
            headers={"Retry-After": str(retry_after)},
        )
    if counter is None:
        counter = UsageCounter(
            org_id=org.org_id, metric="industry_questions", window_start=window, used=0
        )
        session.add(counter)
    counter.used += 1
    session.commit()


@router.post("/questions", response_model=IndustryQuestionResponse)
def questions(
    body: IndustryQuestionRequest,
    org: Annotated[OrgContext, Depends(requires(ANALYSIS_RUN))],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> IndustryQuestionResponse:
    if settings.dry_run or not settings.open_router_key.strip():
        raise HTTPException(
            503, "Live question generation is unavailable. No sample was generated."
        )
    reserve_generation(session, org)
    llm = get_measured_llm(settings)
    try:
        sample, cost = generate_questions(body, llm)
        response = IndustryQuestionResponse(
            **body.model_dump(), questions=sample.questions, model=llm.model, cost_usd=cost
        )
    except Exception as exc:  # noqa: BLE001 — never return provider payloads or credentials
        audit.emit(
            session,
            action="industry_questions:generate",
            context=org,
            actor_type="user",
            actor_id=org.user_id,
            outcome="error",
            detail={"model": llm.model, "cost_usd": getattr(exc, "cost_usd", None)},
        )
        session.commit()
        raise HTTPException(
            502, "Could not generate a valid question set. Please try again."
        ) from None
    audit.emit(
        session,
        action="industry_questions:generate",
        context=org,
        actor_type="user",
        actor_id=org.user_id,
        detail={"model": response.model, "cost_usd": response.cost_usd, "question_count": 10},
    )
    session.commit()
    return response
