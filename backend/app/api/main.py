"""FastAPI application entrypoint (served by uvicorn as ``app.api.main:app``)."""

from fastapi import FastAPI

from app.api.admin_routes import router as admin_router
from app.api.auth_routes import router as auth_router
from app.api.routes import router
from app.api.seo_project_routes import router as seo_project_router

app = FastAPI(title="Yanki API", version="0.1.0")
app.include_router(router)
app.include_router(auth_router)
app.include_router(seo_project_router)
app.include_router(admin_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
