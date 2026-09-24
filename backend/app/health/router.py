"""Liveness/readiness. Tashqi tarmoqqa Caddy orqali ochilmaydi."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
