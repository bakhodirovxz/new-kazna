"""Meta endpointlari: filiallar (RLS + kesh), davrlar, menyu (rolga qarab), freshness."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Response

from app.auth.context import Ctx
from app.core.cache import Cache
from app.core.db import DB
from app.dwh.dates import today_tashkent
from app.dwh.freshness import freshness
from app.meta import service
from app.meta.menu import build_menu
from app.meta.periods import build_periods
from app.meta.schemas import BranchOut, FreshnessOut, MenuOut, PeriodOut, PeriodsOut

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/branches", response_model=list[BranchOut])
def branches(cache: Cache, db: DB) -> Response:
    # Bo'lim endpointlari pattern'i: router → service → pub view, kesh bitta qatorda.
    return cache.respond("meta.branches", {}, lambda: service.list_branches(db))


@router.get("/periods")
def periods(ctx: Ctx) -> PeriodsOut:
    today = today_tashkent()
    items = [PeriodOut(code=p.code, kind=p.kind, label=p.label, date_from=p.date_from,
                       date_to=p.date_to) for p in build_periods(today)]
    return PeriodsOut(default="ytd", today=today, items=items)


@router.get("/menu")
def menu(ctx: Ctx) -> MenuOut:
    return build_menu(ctx.permissions)


@router.get("/freshness")
def data_freshness(ctx: Ctx, db: DB) -> FreshnessOut:
    state = freshness(db.connection(), datetime.now(UTC))
    return FreshnessOut(last_success_at=state.last_success_at, stale=state.stale,
                        max_age_hours=state.max_age_hours, active_build_id=state.active_build_id)
