"""«Производство» (TZ 5): Сводка, Выработка по станциям, Реализация.

Zanjir: router → queries.production (pub view'lar) → Cache.respond (Redis + ETag).
HQ (stansiyasiz filial) tanlansa — has_stations = false, UI tushuntirish chiqaradi (TZ 5).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.context import require_perm
from app.auth.permissions import Section, section_perm
from app.core.cache import Cache
from app.core.db import DB
from app.dwh.reference import current_setting
from app.sections.deps import SQ, SectionQuery
from app.sections.period import ReportPeriod
from app.sections.production_schemas import (
    MapStationOut,
    PowerOut,
    ProizvRealizOut,
    ProizvStanciiOut,
    ProizvSvodOut,
    gen_month_out,
    kpis_out,
    power_out,
    production_out,
    sales_month_out,
    station_out,
)
from app.sections.queries import power, production
from app.sections.queries.cash import opt
from app.sections.schemas import period_out
from app.sections.scope import BranchSel

router = APIRouter(prefix="/proizvodstvo", tags=["proizvodstvo"],
                   dependencies=[Depends(require_perm(section_perm(Section.PROIZVODSTVO)))])
def get_now() -> datetime:
    return datetime.now(UTC)


Now = Annotated[datetime, Depends(get_now)]
SVOD_STATIONS = 8  # prototip: «Выработка по станциям» — 8 ta, «Все станции» tugmasi


def map_stations(db: Session, q: SectionQuery, period: ReportPeriod) -> list[MapStationOut]:
    """Foydalanuvchiga ko'rinadigan barcha filiallar (br tanlovidan qat'i nazar — tanlov UI'da)."""
    every = BranchSel(None, q.branch_ids is None)
    prod = production.station_map(db, every, period)
    rows = db.execute(text(
        "SELECT branch_id, code, name, short_name, kind, capacity_mw, lat, lon FROM pub.branches "
        "ORDER BY sort_order, branch_id")).all()
    return [MapStationOut(branch_id=b.branch_id, code=b.code, name=b.name,
                          short_name=b.short_name, kind=b.kind, capacity_mw=opt(b.capacity_mw),
                          lat=opt(b.lat), lon=opt(b.lon),
                          production=production_out(prod.get(b.branch_id))) for b in rows]


def build_svod(db: Session, q: SectionQuery) -> ProizvSvodOut:
    period, sel = q.period(), q.sel()
    has = production.has_stations(db, sel)
    rows = production.stations(db, sel, period) if has else []
    top = sorted(rows, key=lambda s: (-s.generation, s.name))[:SVOD_STATIONS]
    return ProizvSvodOut(
        period=period_out(period), has_stations=has,
        kpis=kpis_out(production.totals(db, sel, period)),
        months=[gen_month_out(m) for m in production.monthly(db, sel, q.today)],
        stations=[station_out(s) for s in top], map=map_stations(db, q, period))


def build_stancii(db: Session, q: SectionQuery) -> ProizvStanciiOut:
    period, sel = q.period(), q.sel()
    has = production.has_stations(db, sel)
    rows = production.stations(db, sel, period) if has else []
    rows.sort(key=lambda s: (-(s.capacity_mw or 0), s.name))  # prototip: quvvat bo'yicha
    return ProizvStanciiOut(period=period_out(period), has_stations=has,
                            kpis=kpis_out(production.totals(db, sel, period)),
                            stations=[station_out(s) for s in rows])


def build_realiz(db: Session, q: SectionQuery) -> ProizvRealizOut:
    period, sel = q.period(), q.sel()
    has = production.has_stations(db, sel)
    rows = [s for s in production.stations(db, sel, period) if s.accrued > 0] if has else []
    rows.sort(key=lambda s: (s.payment_level if s.payment_level is not None else 9.0, s.name))
    return ProizvRealizOut(
        period=period_out(period), has_stations=has,
        kpis=kpis_out(production.totals(db, sel, period)),
        months=[sales_month_out(m) for m in production.monthly(db, sel, q.today)],
        stations=[station_out(s) for s in rows])


@router.get("/svod", response_model=ProizvSvodOut)
def svod(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("proizvodstvo.svod", q.cache_filters, lambda: build_svod(db, q))


@router.get("/stancii", response_model=ProizvStanciiOut)
def stancii(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("proizvodstvo.stancii", q.cache_filters, lambda: build_stancii(db, q))


@router.get("/realiz", response_model=ProizvRealizOut)
def realiz(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("proizvodstvo.realiz", q.cache_filters, lambda: build_realiz(db, q))


@router.get("/moshchnost", response_model=PowerOut)
def moshchnost(cache: Cache, db: DB, q: SQ, now: Now) -> Response:
    """Jonli quvvat (treplex.uz): build'ga bog'liq emas — kesh kalitiga oxirgi snapshot vaqti va
    eskirganlik kiradi (yangi snapshot yoki eskirish — yangi javob)."""
    stale_minutes = int(current_setting(db.connection(), "askue.live_stale_minutes"))
    latest = power.latest_at(db)
    stale = latest is not None and now - latest > timedelta(minutes=stale_minutes)
    filters = {**q.cache_filters, "snap": latest.isoformat() if latest else None, "stale": stale}
    return cache.respond("proizvodstvo.moshchnost", filters, lambda: power_out(
        power.load(db, q.sel(), now=now, stale_minutes=stale_minutes)))
