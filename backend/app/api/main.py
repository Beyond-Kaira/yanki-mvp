"""FastAPI application entrypoint (served by uvicorn as ``app.api.main:app``)."""

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.admin_routes import router as admin_router
from app.api.auth_routes import router as auth_router
from app.api.backlink_routes import router as backlink_router
from app.api.invitation_routes import router as invitation_router
from app.api.routes import router
from app.api.seo_project_routes import router as seo_project_router
from app.config import Settings, get_settings
from app.db.session import get_session
from app.health import health_report
from app.request_context import RequestContextMiddleware
from app.services.billing import InsufficientCredit, PlanCatalogMissing, QuotaExceeded

app = FastAPI(title="Yanki API", version="0.1.0")

# Outermost middleware, so every request — including ones later middleware or a
# route rejects — carries a request id into the audit trail and back out in the
# response header.
app.add_middleware(RequestContextMiddleware)

app.include_router(router)
app.include_router(auth_router)
app.include_router(seo_project_router)
# Before the SEO project router would also work — the paths do not collide —
# but keeping it after keeps `/api/v1/seo-projects/{id}` reading as one block.
app.include_router(backlink_router)
app.include_router(admin_router)
app.include_router(invitation_router)


# --- Billing failures are HTTP statuses, translated once ---------------------
#
# Registered on the app rather than written into each route, because the failure
# mode of the per-route form is a new metered path that raises `QuotaExceeded`
# and returns 500. A route that wants a more specific sentence still catches the
# exception itself and wins (``backlink_routes.refresh_backlinks`` does); this is
# the floor, not a ceiling.
#
# Three distinct statuses, deliberately not collapsed into one:
#   429 — you have used this month's allowance. Wait, or move up a tier.
#   402 — you cannot afford the call. Top up. (Nothing charges credit on the
#         paths wired in P7.6; it is here so the seam is complete rather than
#         added under pressure later.)
#   503 — the deployment has no plan catalog. Nobody's fault but ours.
# A client that sees one status for all three cannot tell the customer which of
# those three things to do.


@app.exception_handler(QuotaExceeded)
def _quota_exceeded(request: Request, exc: QuotaExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": (
                f"your plan allows {exc.limit} {exc.metric.replace('_', ' ')} "
                f"and {exc.used} have been used"
            ),
            "metric": exc.metric,
            "used": exc.used,
            "limit": exc.limit,
        },
    )


@app.exception_handler(InsufficientCredit)
def _insufficient_credit(request: Request, exc: InsufficientCredit) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        content={
            "detail": f"credit balance {exc.balance} cannot cover an estimated {exc.needed}",
        },
    )


@app.exception_handler(PlanCatalogMissing)
def _plan_catalog_missing(request: Request, exc: PlanCatalogMissing) -> JSONResponse:
    # 503, not 429: this deployment cannot answer the question, which is an
    # operational fault and not a customer's exhausted allowance.
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "billing plans are not configured on this deployment"},
    )


def _is_internal(request: Request) -> bool:
    """Whether this request reached the api without passing the public edge.

    The host nginx vhost path-routes `/healthz` to the api and sets
    `X-Forwarded-For`, so its presence is the signal that a request came from
    outside. `deploy.sh` and `rollback.sh` poll the loopback bind directly and
    set no such header; `deployment.sh` polls the **public** URL and needs only
    the `status`/`ok` markers, which the public body still carries.

    Deliberately not an authentication check. It decides how much *detail* to
    print, never whether to answer, so the worst case of getting it wrong is a
    terser health page — not a locked-out deploy gate.
    """

    if request.headers.get("x-forwarded-for"):
        return False
    peer = request.client.host if request.client else ""
    return peer in {"127.0.0.1", "::1", "testclient"} or peer.startswith("172.")


@app.get("/healthz")
def healthz(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Readiness, not "is uvicorn accepting sockets" (ADR-47).

    This returned the literal `{"status": "ok"}` until P7.8's groundwork, which
    mattered because **it is the deploy gate**: `deploy.sh` and `rollback.sh`
    poll it and record `.last-good` when it answers, so a release with an
    unreachable database was recorded as the good one to roll back *to*.

    Only the components that make the service unservable for everyone can turn
    it red — see `app/health.py` for which and why. The rest report themselves
    and are read by a human.

    **The public body carries the verdict and nothing else.** nginx routes
    `/healthz` from the internet, and the component detail names the schema
    revision, the queue depth, whether provider keys are configured and how
    stale the worker is. None of that is a credential and none of it should be
    handed to anybody who asks either — so the breakdown goes to internal
    callers (the loopback deploy gate, a shell on the box) and everyone else
    gets the status. The verdict is identical for both; only the reasons differ.

    Note the response shape is constrained by `deployment.sh`, which greps the
    body for the substrings `status` and `ok` rather than trusting the status
    code. A failing body must therefore contain no "ok" anywhere;
    `test_health.py` pins that for both shapes.
    """

    body, healthy = health_report(session, settings)
    if not _is_internal(request):
        body = {"status": body["status"]}
    return JSONResponse(
        status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=body,
    )
