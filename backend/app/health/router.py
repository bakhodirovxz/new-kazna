"""Liveness/readiness. Tashqi tarmoqqa Caddy orqali ochilmaydi."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core import ratelimit
from app.core.db import get_engine

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _db_ok() -> bool:
    try:
        with get_engine("app").connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


@router.get("/readyz")
def readyz() -> JSONResponse:
    checks = {"db": _db_ok(), "redis": ratelimit.ping()}
    ok = all(checks.values())
    return JSONResponse(
        {"status": "ok" if ok else "fail", "checks": checks},
        status_code=200 if ok else 503,
    )
