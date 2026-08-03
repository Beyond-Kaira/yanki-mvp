"""HTTP routes for analyses (POST to submit, GET to poll status/results)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.schemas import (
    AnalysisOut,
    CheckerLeadRequest,
    CheckerSubmitRequest,
    CheckerSubmitResponse,
    CompetitorMention,
    CreateAnalysisRequest,
    CreateAnalysisResponse,
    EnginePresence,
    GeoRecordOut,
    PromptOut,
    ResponseOut,
    ResultOut,
    WaitlistRequest,
    WaitlistResponse,
)
from app.config import Settings, get_settings
from app.db.models import Analysis
from app.db.session import get_session
from app.net_guard import is_public_url
from app.services.analyses import create_analysis, get_analysis
from app.services.checker import (
    attach_lead,
    create_checker_analysis,
    find_cached_checker_analysis,
    normalize_triple,
)
from app.services.checker_summary import summarize_checker
from app.services.emailer import send_waitlist_emails
from app.services.rate_limit import (
    WAITLIST_RATE_LIMIT_PER_IP_HOUR,
    RateLimitExceeded,
    check_checker_rate_limit,
    check_rate_limit,
    check_waitlist_rate_limit,
    checker_daily_cost_exceeded,
    client_ip,
    hash_ip,
)
from app.services.waitlist import create_waitlist_signup, normalize_email, signup_count

router = APIRouter(prefix="/api/v1", tags=["analyses"])


def _to_out(analysis: Analysis) -> AnalysisOut:
    """Build the full GET envelope from an ORM row. ``result`` is always present."""
    # Checker-only read-time aggregates (P5.3). Computed for kind='checker' rows
    # from the stored responses; left null for MVP / legacy (kind NULL/'mvp').
    engine_presence: list[EnginePresence] | None = None
    competitors_appeared: list[CompetitorMention] | None = None
    if analysis.kind == "checker":
        summary = summarize_checker(analysis.responses, analysis.kyc)
        engine_presence = [
            EnginePresence.model_validate(stat) for stat in summary.engine_presence
        ]
        competitors_appeared = [
            CompetitorMention.model_validate(stat)
            for stat in summary.competitors_appeared
        ]

    result = ResultOut(
        kyc=analysis.kyc,
        prompts=[PromptOut.model_validate(p) for p in analysis.prompts],
        responses=[ResponseOut.model_validate(r) for r in analysis.responses],
        geo_score=analysis.geo_score,
        footprint_count=analysis.footprint_count,
        total_responses=analysis.total_responses,
        reliability_score=analysis.reliability_score,
        interventions=analysis.interventions,
        citation_summary=analysis.citation_summary,
        geo_records=[GeoRecordOut.model_validate(r) for r in analysis.geo_records],
        engine_presence=engine_presence,
        competitors_appeared=competitors_appeared,
    )
    return AnalysisOut(
        id=analysis.id,
        url=analysis.url,
        status=analysis.status,
        progress=analysis.progress,
        current_step=analysis.current_step,
        error=analysis.error,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
        result=result,
    )


@router.post("/analyses", status_code=202, response_model=CreateAnalysisResponse)
def submit_analysis(
    payload: CreateAnalysisRequest,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CreateAnalysisResponse:
    # Reject SSRF targets (loopback/private/link-local/metadata) up front; the
    # worker's discovery step re-checks every redirect hop as defence in depth.
    # This runs first and returns 422 without creating a row, so SSRF-rejected
    # submits never count toward the rate limit (the limit counts rows).
    if not is_public_url(str(payload.url)):
        raise HTTPException(status_code=422, detail="URL host is not allowed")

    # Rate-limit BEFORE create_analysis so a throttled client never gets a row
    # or spends money — even for an otherwise-valid URL.
    ip_hash = hash_ip(client_ip(request) or "unknown", settings.ip_hash_salt)
    try:
        check_rate_limit(session, ip_hash, settings)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail="rate limit exceeded",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc

    analysis = create_analysis(session, str(payload.url), ip_hash=ip_hash)
    return CreateAnalysisResponse(id=analysis.id)


@router.post("/checker", status_code=202, response_model=CheckerSubmitResponse)
def submit_checker(
    payload: CheckerSubmitRequest,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CheckerSubmitResponse:
    # Blank brand/category is rejected by the schema (422) before we get here, so
    # an invalid submit records nothing.
    #
    # P5.6 hardening: this is an anonymous, LLM-spending public endpoint, so all
    # guards run BEFORE enqueuing. The pivot is whether this triple is a $0 24h
    # cache hit: a cache hit performs no LLM work and MUST always return its id
    # (the email gate posts against the submission), so it is EXEMPT from every
    # guard. A fresh run passes, in order: kill-switch, per-IP + per-brand rate
    # limits, then the daily cost cap. A rejected fresh run records nothing.
    ip_hash = hash_ip(client_ip(request) or "unknown", settings.ip_hash_salt)
    triple = normalize_triple(payload.brand, payload.category, payload.lang)
    is_cache_hit = find_cached_checker_analysis(session, triple, settings) is not None

    if not is_cache_hit:
        if not settings.checker_enabled:
            # Master kill-switch OFF: park the fresh submit and record nothing.
            raise HTTPException(
                status_code=503,
                detail="the free checker is not open yet",
            )
        try:
            check_checker_rate_limit(session, ip_hash, triple, settings)
        except RateLimitExceeded as exc:
            raise HTTPException(
                status_code=429,
                detail="rate limit exceeded",
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc
        if checker_daily_cost_exceeded(session, settings):
            raise HTTPException(
                status_code=503,
                detail="the free checker is at capacity today",
            )

    analysis, submission = create_checker_analysis(
        session, payload.brand, payload.category, payload.lang, settings, ip_hash=ip_hash
    )
    return CheckerSubmitResponse(id=analysis.id, submission_id=submission.id)


@router.post("/checker/leads", status_code=202)
def submit_checker_lead(
    payload: CheckerLeadRequest,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    submission = attach_lead(session, payload.submission_id, payload.email)
    if submission is None:
        raise HTTPException(status_code=404, detail="submission not found")
    return {"status": "ok"}


@router.post("/waitlist", status_code=202, response_model=WaitlistResponse)
def join_waitlist(
    payload: WaitlistRequest,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> WaitlistResponse:
    # Malformed email is a 422 from the schema before we get here, so a bad
    # submit records nothing and never 500s. Rate-limit per IP BEFORE the insert
    # so a throttled client never gets a row.
    ip_hash = hash_ip(client_ip(request) or "unknown", settings.ip_hash_salt)
    try:
        check_waitlist_rate_limit(session, ip_hash, WAITLIST_RATE_LIMIT_PER_IP_HOUR)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail="rate limit exceeded",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc

    signup_id = create_waitlist_signup(session, payload.email, ip_hash=ip_hash)
    # Emails fire ONLY on a genuinely new signup (non-null returned id); a
    # duplicate is silent. Either way we answer 202 {ok: true} — no enumeration.
    if signup_id is not None:
        send_waitlist_emails(normalize_email(payload.email), signup_count(session), settings)
    return WaitlistResponse(ok=True)


@router.get("/analyses/{analysis_id}", response_model=AnalysisOut)
def read_analysis(
    analysis_id: uuid.UUID,
    session: Session = Depends(get_session),
) -> AnalysisOut:
    analysis = get_analysis(session, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    return _to_out(analysis)
