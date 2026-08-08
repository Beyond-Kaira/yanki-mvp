"""HTTP routes for analyses (POST to submit, GET to poll status/results).

**Submitting an analysis requires authentication (ADR-45).** It did not until
P7.6, and the gap was invisible because no page had needed it since session 21
moved the URL form behind sign-in: the route stayed open while every caller of
it stopped being anonymous. An unauthenticated endpoint that spends money at a
paid vendor cannot be metered — there is no tenant to meter — so closing it is
the precondition for a plan tier meaning anything, not a separate hardening.

Reading one is a different question and keeps a different answer. An analysis
with no ``org_id`` is a capability URL: hold the id, read the result. That is
every row in production today, and every checker run. An analysis that carries
an organization belongs to it alone. ``tenancy.readable_analysis`` is the single
place that rule lives, and this module's job is to hand it the caller's context.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.org_dependencies import get_optional_org_context, requires
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
    SeoAuditOut,
    SeoCheckOut,
    SerpCheckOut,
    SerpVisibilityOut,
    WaitlistRequest,
    WaitlistResponse,
)
from app.config import Settings, get_settings
from app.db.models import Analysis
from app.db.session import get_session
from app.net_guard import is_public_url
from app.services import audit, billing, quota
from app.services.analyses import create_analysis
from app.services.checker import (
    attach_lead,
    create_checker_analysis,
    find_cached_checker_analysis,
    normalize_triple,
)
from app.services.checker_summary import summarize_checker
from app.services.emailer import send_waitlist_emails
from app.services.permissions import ANALYSIS_RUN
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
from app.services.tenancy import OrgContext, readable_analysis
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

    # SERP visibility (ADR-28). Present only when the run actually measured it:
    # a null summary says "we did not look", which must never render as a zero.
    serp: SerpVisibilityOut | None = None
    if analysis.serp_status is not None:
        serp = SerpVisibilityOut(
            status=analysis.serp_status,
            source=analysis.serp_source,
            score=analysis.serp_score,
            hits=analysis.serp_hit_count or 0,
            queries=analysis.serp_query_count or 0,
            checks=[SerpCheckOut.model_validate(c) for c in analysis.serp_checks],
        )

    # SEO audit (ADR-31). Present only when the run actually audited a site.
    seo: SeoAuditOut | None = None
    if analysis.seo_status is not None:
        seo = SeoAuditOut(
            status=analysis.seo_status,
            score=analysis.seo_score,
            grade=analysis.seo_grade,
            checks=[SeoCheckOut.model_validate(c) for c in analysis.seo_checks],
        )

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
        serp=serp,
        seo=seo,
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
    org: OrgContext = Depends(requires(ANALYSIS_RUN)),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CreateAnalysisResponse:
    """Queue one GEO analysis for the caller's organization.

    The guards run cheapest-and-most-certain first, and each one refuses before
    the next has any effect:

    1. **SSRF** — 422, and no row, so a rejected target never counts anywhere.
    2. **Per-credential burst** — the P5.0 IP limit, unchanged. A monthly plan
       quota does not bound a burst; five hundred runs on the first of the month
       is inside a Business allowance and still a stampede at the vendor.
    3. **Plan quota** — 429 (ADR-45). Consumed here, committed with the row.
    """

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

    # The counter and the row it pays for commit together, or neither does.
    # `create_analysis(commit=False)` exists for exactly this: a commit inside it
    # would let the run be created and the quota rolled back by a later failure.
    org_id = org.require_org_id
    quota.consume(session, settings, org_id=org_id, metric=billing.METRIC_ANALYSES)
    analysis = create_analysis(
        session, str(payload.url), ip_hash=ip_hash, org_id=org_id, commit=False
    )

    audit.emit(
        session,
        action="analysis:create",
        context=org,
        actor_type="user",
        actor_id=org.user_id,
        entity_type="analysis",
        entity_id=analysis.id,
        after={"url": analysis.url, "kind": analysis.kind or "mvp"},
    )
    session.commit()
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
    org: OrgContext | None = Depends(get_optional_org_context),
    session: Session = Depends(get_session),
) -> AnalysisOut:
    """One analysis, if this caller may see it.

    404 covers both "no such analysis" and "not yours" on purpose. Splitting
    them would turn this route into an oracle for which analysis ids exist,
    which is the whole value of an unguessable id.
    """

    analysis = readable_analysis(session, analysis_id, org)
    if analysis is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    return _to_out(analysis)
