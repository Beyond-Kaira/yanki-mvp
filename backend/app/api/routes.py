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

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.analysis_slices import (
    build_envelope,
    build_geo_out,
    build_kyc_out,
    build_prompts_out,
    build_seo_out,
    build_serp_out,
)
from app.api.org_dependencies import get_optional_org_context, requires
from app.api.schemas import (
    AnalysisKycOut,
    AnalysisListOut,
    AnalysisOut,
    AnalysisPromptsOut,
    AnalysisSummaryOut,
    CheckerLeadRequest,
    CheckerSubmitRequest,
    CheckerSubmitResponse,
    CreateAnalysisRequest,
    CreateAnalysisResponse,
    GeoOut,
    SeoAuditOut,
    SerpVisibilityOut,
    WaitlistRequest,
    WaitlistResponse,
)
from app.config import Settings, get_settings
from app.db.models import Analysis
from app.db.session import get_session
from app.net_guard import is_public_url
from app.services import audit, billing, quota
from app.services.analyses import MAX_PAGE, create_analysis, list_org_analyses
from app.services.checker import (
    attach_lead,
    create_checker_analysis,
    find_cached_checker_analysis,
    normalize_triple,
)
from app.services.emailer import send_waitlist_emails
from app.services.permissions import ANALYSIS_READ, ANALYSIS_RUN
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
    """Build the thin GET envelope from an ORM row."""
    return build_envelope(analysis)


def _readable_or_404(
    session: Session,
    analysis_id: uuid.UUID,
    org: OrgContext | None,
) -> Analysis:
    analysis = readable_analysis(session, analysis_id, org)
    if analysis is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    return analysis


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
    quota.consume(session, settings, org_id=org_id, metric=billing.METRIC_ANALYSES, context=org)
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

    # The one path on which this platform spends vendor money for somebody who
    # has no account. `cache_hit` is the field that matters: a miss is an LLM
    # bill, a hit is a database read, and without the distinction the log cannot
    # answer "why did our checker cost go up" — which is the question this event
    # exists for. Both are recorded, so "every mutating path emits" stays
    # literally true rather than true-with-an-asterisk.
    #
    # NULL org and an anonymous actor, because that is the truth: nobody owns
    # this. It is bounded by the guards above (kill switch, per-IP and per-brand
    # rate limits, daily cost cap), so a public endpoint cannot flood the trail.
    audit.emit(
        session,
        action="checker:submit",
        actor_type="anonymous",
        entity_type="analysis",
        entity_id=analysis.id,
        after={"brand": analysis.brand, "category": analysis.category, "lang": analysis.lang},
        detail={"cache_hit": is_cache_hit, "submission": str(submission.id)},
    )
    session.commit()
    return CheckerSubmitResponse(id=analysis.id, submission_id=submission.id)


@router.post("/checker/leads", status_code=202)
def submit_checker_lead(
    payload: CheckerLeadRequest,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    submission = attach_lead(session, payload.submission_id, payload.email)
    if submission is None:
        raise HTTPException(status_code=404, detail="submission not found")

    # The event records that an address was attached, and deliberately does NOT
    # record the address. Two reasons, and the second is the load-bearing one:
    #
    # 1. It adds nothing. `checker_submissions.email` holds it, and this row
    #    points straight at that submission.
    # 2. `audit_events` is append-only, enforced by database triggers (migration
    #    0018) — a row written here can never be deleted, by anyone, through the
    #    application. Copying an email in would make it un-erasable and put the
    #    future erasure path (`pii-retention-and-erasure`) in direct conflict
    #    with the integrity guarantee. Keeping the reference and dropping the
    #    value lets both hold: erase the submission, and this row still truthfully
    #    says an address was attached and then removed.
    #
    # Failed logins are the deliberate exception — there the attempted address
    # IS the evidence, and there is no other row carrying it.
    audit.emit(
        session,
        action="checker:lead",
        actor_type="anonymous",
        entity_type="checker_submission",
        entity_id=submission.id,
        detail={"analysis": str(submission.analysis_id), "email_recorded": True},
    )
    session.commit()
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
        # Audited on the same condition, and for the same reason: a duplicate
        # inserted no row, so there is no mutation to record. Recording it anyway
        # would also put "this address was already on the list" into a table —
        # which is the enumeration answer this endpoint spends its whole design
        # refusing to give.
        #
        # The address is not stored here; `waitlist_signups` holds it and this
        # row points at it. See the `checker:lead` emit above for why an
        # append-only table is the wrong place to copy erasable PII into.
        audit.emit(
            session,
            action="waitlist:signup",
            actor_type="anonymous",
            entity_type="waitlist_signup",
            entity_id=signup_id,
        )
        session.commit()
        send_waitlist_emails(normalize_email(payload.email), signup_count(session), settings)
    return WaitlistResponse(ok=True)


@router.get("/analyses", response_model=AnalysisListOut)
def list_analyses(
    status: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=20, ge=1, le=MAX_PAGE),
    offset: int = Query(default=0, ge=0),
    org: OrgContext = Depends(requires(ANALYSIS_READ)),
    session: Session = Depends(get_session),
) -> AnalysisListOut:
    """The caller's organization's analyses, newest first.

    Signed-in and org-scoped, unlike the sibling detail route. That asymmetry is
    deliberate and worth stating, because the two look like they should match:
    ``GET /analyses/{id}`` still serves an org-less run to anyone holding its id
    (a capability URL — the product's entire pre-P7.6 surface, and every row in
    production today), while a *list* has no capability to hold. There is no
    id to know, so the only possible answer to "whose analyses?" is the caller's
    organization, and an unauthenticated version of this route could only ever
    mean "everyone's".

    Runs from before P7.6 carry no ``org_id`` and therefore appear in nobody's
    history. That is the honest rendering: they belong to no tenant, and
    inventing an owner for them would be a worse answer than omitting them.
    """

    page = list_org_analyses(session, org, status=status, limit=limit, offset=offset)
    return AnalysisListOut(
        total=page.total,
        limit=limit,
        offset=offset,
        analyses=[AnalysisSummaryOut.model_validate(row) for row in page.analyses],
    )


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

    analysis = _readable_or_404(session, analysis_id, org)
    return _to_out(analysis)


@router.get("/analyses/{analysis_id}/kyc", response_model=AnalysisKycOut)
def read_analysis_kyc(
    analysis_id: uuid.UUID,
    org: OrgContext | None = Depends(get_optional_org_context),
    session: Session = Depends(get_session),
) -> AnalysisKycOut:
    """Company profile (KYC) for one analysis — same ``result.kyc`` as the full GET."""

    analysis = _readable_or_404(session, analysis_id, org)
    return build_kyc_out(analysis)


@router.get("/analyses/{analysis_id}/prompts", response_model=AnalysisPromptsOut)
def read_analysis_prompts(
    analysis_id: uuid.UUID,
    org: OrgContext | None = Depends(get_optional_org_context),
    session: Session = Depends(get_session),
) -> AnalysisPromptsOut:
    """Generated prompts for one analysis."""

    analysis = _readable_or_404(session, analysis_id, org)
    return build_prompts_out(analysis)


@router.get("/analyses/{analysis_id}/geo", response_model=GeoOut)
def read_analysis_geo(
    analysis_id: uuid.UUID,
    org: OrgContext | None = Depends(get_optional_org_context),
    session: Session = Depends(get_session),
) -> GeoOut:
    """Measured GEO slice (responses, geo_records, scores, interventions)."""

    analysis = _readable_or_404(session, analysis_id, org)
    return build_geo_out(analysis)


@router.get("/analyses/{analysis_id}/serp", response_model=SerpVisibilityOut | None)
def read_analysis_serp(
    analysis_id: uuid.UUID,
    org: OrgContext | None = Depends(get_optional_org_context),
    session: Session = Depends(get_session),
) -> SerpVisibilityOut | None:
    """SERP visibility when measured; ``null`` when the run did not look (ADR-28)."""

    analysis = _readable_or_404(session, analysis_id, org)
    return build_serp_out(analysis)


@router.get("/analyses/{analysis_id}/seo", response_model=SeoAuditOut | None)
def read_analysis_seo(
    analysis_id: uuid.UUID,
    org: OrgContext | None = Depends(get_optional_org_context),
    session: Session = Depends(get_session),
) -> SeoAuditOut | None:
    """Homepage SEO audit when run; ``null`` when not audited (ADR-31). Not Site Audit."""

    analysis = _readable_or_404(session, analysis_id, org)
    return build_seo_out(analysis)
