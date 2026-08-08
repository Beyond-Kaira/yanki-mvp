"""FastAPI application entrypoint (served by uvicorn as ``app.api.main:app``)."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.admin_routes import router as admin_router
from app.api.auth_routes import router as auth_router
from app.api.backlink_routes import router as backlink_router
from app.api.invitation_routes import router as invitation_router
from app.api.routes import router
from app.api.seo_project_routes import router as seo_project_router
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


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
