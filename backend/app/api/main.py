"""FastAPI application entrypoint (served by uvicorn as ``app.api.main:app``)."""

from fastapi import FastAPI

from app.api.admin_routes import router as admin_router
from app.api.auth_routes import router as auth_router
from app.api.backlink_routes import router as backlink_router
from app.api.invitation_routes import router as invitation_router
from app.api.routes import router
from app.api.search_console_routes import callback_router as search_console_callback_router
from app.api.search_console_routes import router as search_console_router
from app.api.seo_project_routes import router as seo_project_router
from app.request_context import RequestContextMiddleware

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
app.include_router(search_console_router)
# The OAuth return leg is not nested under a project: it is the URL registered
# with Google, it authenticates nobody, and it recovers its context from the
# state row alone. Kept separate so that difference is visible in the wiring.
app.include_router(search_console_callback_router)
app.include_router(admin_router)
app.include_router(invitation_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
