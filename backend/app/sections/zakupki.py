"""«Закупки» (TZ 5): Сводка, Лоты, Договоры и поставщики, Экономия.

Zanjir: router → queries.procurement (pub view'lar) → Cache.respond (Redis + ETag).
Lotlar filtri («все, в работе, просроченные, заключённые») — klientda, `kind`/`overdue` bo'yicha.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.context import require_perm
from app.auth.permissions import Section, section_perm
from app.core.cache import Cache
from app.core.db import DB
from app.sections.deps import SQ, SectionQuery
from app.sections.queries import procurement
from app.sections.schemas import period_out
from app.sections.zakupki_schemas import (
    ZakBranchOut,
    ZakEkonomiyaOut,
    ZakLotyOut,
    ZakMonthOut,
    ZakNamedOut,
    ZakPostavshikiOut,
    ZakSvodOut,
    lot_out,
    method_out,
    zak_kpis_out,
)

router = APIRouter(prefix="/zakupki", tags=["zakupki"],
                   dependencies=[Depends(require_perm(section_perm(Section.ZAKUPKI)))])
SVOD_LOTS = 8  # prototip: «Лоты» kartasida 8 ta + «Все лоты»


def _named(rows: list[procurement.NamedCount]) -> list[ZakNamedOut]:
    return [ZakNamedOut(name=r.name, amount=r.amount, count=r.count) for r in rows]


def build_svod(db: Session, q: SectionQuery) -> ZakSvodOut:
    period, sel = q.period(), q.sel()
    return ZakSvodOut(
        period=period_out(period), kpis=zak_kpis_out(procurement.totals(db, sel, period)),
        months=[ZakMonthOut(month_id=m.month_id, contracted=m.contracted)
                for m in procurement.monthly(db, sel, q.today)],
        methods=[method_out(m) for m in procurement.by_method(db, sel, period)],
        lots=[lot_out(r) for r in procurement.lots(db, sel, period, limit=SVOD_LOTS)])


def build_loty(db: Session, q: SectionQuery) -> ZakLotyOut:
    period, sel = q.period(), q.sel()
    rows = procurement.lots(db, sel, period, limit=procurement.LOTS_LIMIT + 1)
    return ZakLotyOut(period=period_out(period),
                      kpis=zak_kpis_out(procurement.totals(db, sel, period)),
                      lots=[lot_out(r) for r in rows[:procurement.LOTS_LIMIT]],
                      truncated=len(rows) > procurement.LOTS_LIMIT)


def build_postavshiki(db: Session, q: SectionQuery) -> ZakPostavshikiOut:
    period, sel = q.period(), q.sel()
    return ZakPostavshikiOut(
        period=period_out(period), kpis=zak_kpis_out(procurement.totals(db, sel, period)),
        suppliers=_named(procurement.suppliers(db, sel, period)),
        subjects=_named(procurement.subjects(db, sel, period)),
        branches=[ZakBranchOut(branch_id=b.branch_id, name=b.name, plan=b.plan, ytd=b.ytd,
                               execution=b.execution, savings=b.savings)
                  for b in procurement.by_branch(db, sel, period)])


def build_ekonomiya(db: Session, q: SectionQuery) -> ZakEkonomiyaOut:
    period, sel = q.period(), q.sel()
    return ZakEkonomiyaOut(
        period=period_out(period), kpis=zak_kpis_out(procurement.totals(db, sel, period)),
        methods=[method_out(m) for m in procurement.by_method(db, sel, period)],
        cancelled=[lot_out(r) for r in procurement.cancelled(db, sel, period)])


@router.get("/svod", response_model=ZakSvodOut)
def svod(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("zakupki.svod", q.cache_filters, lambda: build_svod(db, q))


@router.get("/loty", response_model=ZakLotyOut)
def loty(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("zakupki.loty", q.cache_filters, lambda: build_loty(db, q))


@router.get("/postavshiki", response_model=ZakPostavshikiOut)
def postavshiki(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("zakupki.postavshiki", q.cache_filters,
                         lambda: build_postavshiki(db, q))


@router.get("/ekonomiya", response_model=ZakEkonomiyaOut)
def ekonomiya(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("zakupki.ekonomiya", q.cache_filters, lambda: build_ekonomiya(db, q))
