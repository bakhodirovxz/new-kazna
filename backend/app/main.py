"""FastAPI ilovasi."""

from __future__ import annotations

from fastapi import FastAPI

from app import __version__
from app.health.router import router as health_router

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(
        title="UGEKAZNA API",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(health_router, prefix=API_PREFIX)
    return app


app = create_app()
