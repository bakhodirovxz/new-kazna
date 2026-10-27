"""FastAPI ilovasi."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.concurrency import run_in_threadpool

from app import __version__
from app.admin.config_router import router as config_router
from app.admin.etl_router import router as etl_router
from app.admin.keys_router import router as keys_router
from app.admin.router import router as admin_router
from app.audit.router import router as audit_router
from app.auth.context import require_perm
from app.auth.permissions import Perm
from app.auth.router import router as auth_router
from app.bootstrap import bootstrap_runtime
from app.core.config import ConfigError, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import (
    MAX_BODY_BYTES,
    BodySizeLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.health.router import router as health_router
from app.meta.router import router as meta_router
from app.sections.kazna import router as kazna_router
from app.sections.obzor import router as obzor_router

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    problems = get_settings().problems()
    if problems:
        raise ConfigError("; ".join(problems))
    await run_in_threadpool(bootstrap_runtime)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    app = FastAPI(
        title="UGEKAZNA API",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    register_error_handlers(app)
    # Oxirgi qo'shilgan — eng tashqi: RequestContext birinchi ishlaydi, so'ng SecurityHeaders
    # (BodySizeLimit'ning 413 javobini ham qamrab oladi), so'ng BodySizeLimit.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_BODY_BYTES)
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.base_url.startswith("https://"))
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router, prefix=API_PREFIX)
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(admin_router, prefix=API_PREFIX)
    app.include_router(audit_router, prefix=API_PREFIX)
    app.include_router(keys_router, prefix=API_PREFIX)
    app.include_router(meta_router, prefix=API_PREFIX)
    app.include_router(obzor_router, prefix=API_PREFIX)
    app.include_router(kazna_router, prefix=API_PREFIX)
    app.include_router(etl_router, prefix=API_PREFIX)
    app.include_router(config_router, prefix=API_PREFIX)
    _mount_openapi(app, protected=settings.env == "prod")
    return app


def _mount_openapi(app: FastAPI, *, protected: bool) -> None:
    dependencies = [Depends(require_perm(Perm.ADMIN_SETTINGS))] if protected else []

    @app.get(f"{API_PREFIX}/openapi.json", include_in_schema=False, dependencies=dependencies)
    def openapi() -> dict[str, Any]:
        return app.openapi()


app = create_app()
