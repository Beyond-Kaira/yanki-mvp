"""FastAPI application entrypoint (served by uvicorn as ``app.api.main:app``)."""

from fastapi import FastAPI

from app.api.auth_routes import router as auth_router
from app.api.routes import router

app = FastAPI(title="Yanki API", version="0.1.0")
app.include_router(router)
app.include_router(auth_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
