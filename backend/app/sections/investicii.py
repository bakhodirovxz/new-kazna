"""«Инвестиции» (TZ 5): Сводка, Объекты, Источники и освоение, Сроки и риски.

Zanjir: router → queries.investment (pub view'lar) → Cache.respond. Obyektsiz filial — has_objects
false, UI: «У выбранного филиала нет объектов адресной программы».
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.context import require_perm
from app.auth.permissions import Section, section_perm
from app.core.cache import Cache
from app.core.db import DB
from app.sections.deps import SQ, SectionQuery
from app.sections.investicii_schemas import (
    InvCumOut,
    InvIstochnikiOut,
    InvObektyOut,
    InvObjectStagesOut,
    InvRiskiOut,
    InvSourceOut,
    InvStageOut,
    InvSvodOut,
    inv_kpis_out,
    object_out,
)
from app.sections.period import ReportPeriod
from app.sections.queries import investment
from app.sections.schemas import period_out
from app.sections.scope import BranchSel

router = APIRouter(prefix="/investicii", tags=["investicii"],
                   dependencies=[Depends(require_perm(section_perm(Section.INVESTICII)))])
SVOD_OBJECTS = 6  # prototip: «Объекты программы» — 6 ta + «Все объекты»
RISK_STAGES = 8  # prototip stageCard — 8 ta


def _load(db: Session, q: SectionQuery) -> tuple[ReportPeriod, BranchSel,
                                                 list[investment.InvObject],
                                                 investment.InvTotals]:
    period, sel = q.period(), q.sel()
    rows = investment.objects(db, sel, period)
    return period, sel, rows, investment.totals(rows, period)


def _cum(db: Session, sel: BranchSel, q: SectionQuery, year: int) -> list[InvCumOut]:
    return [InvCumOut(month_id=p.month_id, plan=p.plan, fact=p.fact)
            for p in investment.cumulative(db, sel, year, q.today)]


def _sources(rows: list[investment.InvObject]) -> list[InvSourceOut]:
    return [InvSourceOut(name=s.name, plan_year=s.plan_year, fact_ytd=s.fact_ytd, share=s.share)
            for s in investment.sources(rows)]


def build_svod(db: Session, q: SectionQuery) -> InvSvodOut:
    period, sel, rows, t = _load(db, q)
    return InvSvodOut(period=period_out(period), kpis=inv_kpis_out(t),
                      cumulative=_cum(db, sel, q, t.year), sources=_sources(rows),
                      objects=[object_out(o) for o in rows[:SVOD_OBJECTS]])


def build_obekty(db: Session, q: SectionQuery) -> InvObektyOut:
    period, _sel, rows, t = _load(db, q)
    return InvObektyOut(period=period_out(period), kpis=inv_kpis_out(t),
                        objects=[object_out(o) for o in rows])


def build_istochniki(db: Session, q: SectionQuery) -> InvIstochnikiOut:
    period, sel, rows, t = _load(db, q)
    by_fact = sorted(rows, key=lambda o: (-o.fact_ytd, o.name))
    return InvIstochnikiOut(period=period_out(period), kpis=inv_kpis_out(t),
                            sources=_sources(rows), objects=[object_out(o) for o in by_fact],
                            cumulative=_cum(db, sel, q, t.year))


def build_riski(db: Session, q: SectionQuery) -> InvRiskiOut:
    period, sel, rows, t = _load(db, q)
    lagging = sorted((o for o in rows if o.status in ("lag", "risk")),
                     key=lambda o: (o.execution or 0.0, o.name))
    gaps = sorted((o for o in rows if o.gap_pp is not None and o.gap_pp > investment.GAP_PP),
                  key=lambda o: (-(o.gap_pp or 0.0), o.name))
    advances = sorted((o for o in rows if o.advance > 0 and o.advance_days is not None
                       and o.advance_days > investment.ADVANCE_DAYS),
                      key=lambda o: (-o.advance, o.name))
    by_obj = {o.object_id: o for o in rows}
    stage_rows = [
        InvObjectStagesOut(
            object_id=oid, name=by_obj[oid].name, branch_id=by_obj[oid].branch_id,
            late=sum(1 for s in items if s.late),
            stages=[InvStageOut(stage_no=s.stage_no, name=s.name, plan_date=s.plan_date,
                                fact_date=s.fact_date, done=s.done, late=s.late)
                    for s in items])
        for oid, items in investment.stages(db, sel).items() if oid in by_obj]
    stage_rows.sort(key=lambda s: (-s.late, -by_obj[s.object_id].plan_year, s.name))
    return InvRiskiOut(period=period_out(period), kpis=inv_kpis_out(t),
                       lagging=[object_out(o) for o in lagging],
                       gaps=[object_out(o) for o in gaps], stages=stage_rows[:RISK_STAGES],
                       advances=[object_out(o) for o in advances])


@router.get("/svod", response_model=InvSvodOut)
def svod(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("investicii.svod", q.cache_filters, lambda: build_svod(db, q))


@router.get("/obekty", response_model=InvObektyOut)
def obekty(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("investicii.obekty", q.cache_filters, lambda: build_obekty(db, q))


@router.get("/istochniki", response_model=InvIstochnikiOut)
def istochniki(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("investicii.istochniki", q.cache_filters,
                         lambda: build_istochniki(db, q))


@router.get("/riski", response_model=InvRiskiOut)
def riski(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("investicii.riski", q.cache_filters, lambda: build_riski(db, q))
