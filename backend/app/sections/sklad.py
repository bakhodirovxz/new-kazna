"""«Склад» (TZ 5): Сводка, Остатки по складам, Минимальный запас, Неликвиды.

Zanjir: router → queries.stock (pub view'lar) → Cache.respond (Redis + ETag).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.context import require_perm
from app.auth.permissions import Section, section_perm
from app.core.cache import Cache
from app.core.db import DB
from app.sections.deps import SQ, SectionQuery
from app.sections.queries import stock
from app.sections.schemas import period_out
from app.sections.stock_schemas import (
    AgeBucketOut,
    SkladMinimumOut,
    SkladNelikvidOut,
    SkladOstatkiOut,
    SkladSvodOut,
    StockBranchOut,
    StockMonthOut,
    named_values_out,
    position_out,
    stock_kpis_out,
)

router = APIRouter(prefix="/sklad", tags=["sklad"],
                   dependencies=[Depends(require_perm(section_perm(Section.SKLAD)))])
SVOD_BELOW = 5  # prototip: «Самые дефицитные позиции» — 5 ta, «Все позиции»


def build_svod(db: Session, q: SectionQuery) -> SkladSvodOut:
    period, sel = q.period(), q.sel()
    return SkladSvodOut(
        period=period_out(period), kpis=stock_kpis_out(stock.totals(db, sel, period)),
        months=[StockMonthOut(month_id=m.month_id, inflow=m.inflow, outflow=m.outflow)
                for m in stock.flows(db, sel, q.today)],
        categories=named_values_out(stock.categories(db, sel, period.last_month)),
        below=[position_out(p) for p in stock.positions(db, sel, period.last_month, "below",
                                                        limit=SVOD_BELOW)])


def build_ostatki(db: Session, q: SectionQuery) -> SkladOstatkiOut:
    period, sel = q.period(), q.sel()
    return SkladOstatkiOut(
        period=period_out(period), kpis=stock_kpis_out(stock.totals(db, sel, period)),
        branches=[StockBranchOut(branch_id=b.branch_id, name=b.name, value=b.value,
                                 positions=b.positions, below_min=b.below_min,
                                 idle_value=b.idle_value)
                  for b in stock.by_branch(db, sel, period)],
        categories=named_values_out(stock.categories(db, sel, period.last_month)))


def build_minimum(db: Session, q: SectionQuery) -> SkladMinimumOut:
    period, sel = q.period(), q.sel()
    return SkladMinimumOut(
        period=period_out(period), kpis=stock_kpis_out(stock.totals(db, sel, period)),
        below=[position_out(p) for p in stock.positions(db, sel, period.last_month, "below")])


def build_nelikvid(db: Session, q: SectionQuery) -> SkladNelikvidOut:
    period, sel = q.period(), q.sel()
    return SkladNelikvidOut(
        period=period_out(period), kpis=stock_kpis_out(stock.totals(db, sel, period)),
        ages=[AgeBucketOut(key=a.key, value=a.value)
              for a in stock.ages(db, sel, period.last_month)],
        illiquid=[position_out(p) for p in stock.positions(db, sel, period.last_month, "idle")])


@router.get("/svod", response_model=SkladSvodOut)
def svod(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("sklad.svod", q.cache_filters, lambda: build_svod(db, q))


@router.get("/ostatki", response_model=SkladOstatkiOut)
def ostatki(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("sklad.ostatki", q.cache_filters, lambda: build_ostatki(db, q))


@router.get("/minimum", response_model=SkladMinimumOut)
def minimum(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("sklad.minimum", q.cache_filters, lambda: build_minimum(db, q))


@router.get("/nelikvid", response_model=SkladNelikvidOut)
def nelikvid(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("sklad.nelikvid", q.cache_filters, lambda: build_nelikvid(db, q))
