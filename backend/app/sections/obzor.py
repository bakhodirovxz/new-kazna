"""«Обзор» (TZ 5): Сводка, Поступления, Расходование, Таблица Excel, statya → filiallar.

Zanjir: router → queries (pub view'lar) → Cache.respond (Redis + ETag). «Требует внимания»
va xlsx eksport — alohida modullarda (app/alerts, app/sections/exports).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.context import Ctx, require_perm
from app.auth.permissions import Section, section_perm
from app.core.cache import Cache
from app.core.db import DB
from app.sections.deps import SQ, SectionQuery
from app.sections.period import ReportPeriod
from app.sections.queries import cash, debt
from app.sections.queries.cash import ACTIVITIES
from app.sections.schemas import (
    ActivityAmountOut,
    AlertCountOut,
    AlertsOut,
    BankAmountOut,
    BranchAmountOut,
    BranchCashOut,
    DetailRowOut,
    ItemBranchesOut,
    ItemBranchRowOut,
    ItemInfoOut,
    MonthPointOut,
    ObzorExcelOut,
    ObzorFlowOut,
    ObzorSvodOut,
    SeriesOut,
    StationOut,
    branch_cash_out,
    items_out,
    kpis_out,
    period_out,
)
from app.sections.scope import BranchSel

router = APIRouter(prefix="/obzor", tags=["obzor"],
                   dependencies=[Depends(require_perm(section_perm(Section.OBZOR)))])
ACTIVITY_TITLES = {"centralized": "Централизованная", "operating": "Операционная",
                   "investing": "Инвестиционная"}
OTHERS = "Остальные статьи"


def _activity(rows: list[cash.ActivityAmount]) -> list[ActivityAmountOut]:
    return [ActivityAmountOut(activity=a.activity, amount=a.amount) for a in rows]


def stations(db: Session, q: SectionQuery, period: ReportPeriod) -> list[StationOut]:
    """Xaritadagi barcha ko'rinadigan stansiyalar (br tanlovidan qat'i nazar; tanlov — UI'da)."""
    every = BranchSel(None, q.branch_ids is None)
    money = {r.branch_id: r for r in cash.by_branch(db, every, period)}
    debts = {r.branch_id: r for r in debt.debt_by_branch(db, every, period.last_month)}
    out: list[StationOut] = []
    for b in db.execute(text(
            "SELECT branch_id, code, name, short_name, kind, capacity_mw, lat, lon "
            "FROM pub.branches "
            "ORDER BY sort_order, branch_id")).all():
        m, d = money.get(b.branch_id), debts.get(b.branch_id)
        out.append(StationOut(
            branch_id=b.branch_id, code=b.code, name=b.name, short_name=b.short_name, kind=b.kind,
            capacity_mw=cash.opt(b.capacity_mw), lat=cash.opt(b.lat), lon=cash.opt(b.lon),
            inflow=m.inflow if m else None, outflow=m.outflow if m else None,
            closing=m.closing if m else None,
            receivable=d.receivable if d else None, payable=d.payable if d else None,
            overdue_payable=d.overdue_payable if d else None))
    return out


def build_svod(db: Session, q: SectionQuery) -> ObzorSvodOut:
    period, sel = q.period(), q.sel()
    out_items = cash.items(db, sel, period, "out")
    return ObzorSvodOut(
        period=period_out(period),
        kpis=kpis_out(cash.cash_totals(db, sel, period)),
        months=[MonthPointOut(month_id=p.month_id, inflow=p.inflow, outflow=p.outflow,
                              closing=p.closing, inflow_prev=p.inflow_prev,
                              outflow_prev=p.outflow_prev)
                for p in cash.monthly(db, sel, q.today)],
        activity=_activity(cash.activity_split(out_items)),
        branches=[branch_cash_out(r) for r in cash.by_branch(db, sel, period)],
        items_in=items_out(cash.items(db, sel, period, "in")),
        items_out=items_out(out_items),
        stations=stations(db, q, period),
    )


def build_flow(db: Session, q: SectionQuery, direction: str) -> ObzorFlowOut:
    period, sel = q.period(), q.sel()
    months = [q.today.year * 100 + m for m in range(1, q.today.month + 1)]
    period_items = cash.items(db, sel, period, direction)
    by_item = cash.item_months(db, sel, months, direction)
    if direction == "in":
        top = [i.item_id for i in period_items[:3]]
        names = {i.item_id: i.name for i in period_items}
        series = [SeriesOut(key=str(i), name=names[i],
                            values=[by_item.get(i, {}).get(m, 0.0) for m in months]) for i in top]
        rest = [i for i in by_item if i not in top]
        if rest:
            series.append(SeriesOut(key="others", name=OTHERS, values=[
                round(sum(by_item[i].get(m, 0.0) for i in rest), 2) for m in months]))
        activity: list[ActivityAmountOut] = []
    else:
        info = {r.item_id: r.activity for r in cash.items(
            db, sel, _year_period(q, months), direction)}
        series = [SeriesOut(key=a, name=ACTIVITY_TITLES[a], values=[
            round(sum(v.get(m, 0.0) for i, v in by_item.items() if info.get(i) == a), 2)
            for m in months]) for a in ACTIVITIES]
        activity = _activity(cash.activity_split(period_items))
    flow = "inflow" if direction == "in" else "outflow"
    return ObzorFlowOut(
        period=period_out(period), kpis=kpis_out(cash.cash_totals(db, sel, period)),
        direction=direction, months=months, series=series, items=items_out(period_items),
        activity=activity,
        banks=[BankAmountOut(bank_name=b.bank_name, amount=getattr(b, flow), closing=b.closing)
               for b in cash.banks(db, sel, period) if getattr(b, flow) > 0],
        branches=sorted((BranchAmountOut(branch_id=r.branch_id, name=r.name,
                                         amount=getattr(r, flow))
                         for r in cash.by_branch(db, sel, period)),
                        key=lambda r: -r.amount),
    )


def _year_period(q: SectionQuery, months: list[int]) -> ReportPeriod:
    """Yil boshidan joriy oygacha (statyalarning faoliyat turini aniqlash uchun)."""
    period = q.period()
    return ReportPeriod("ytd", period.label, period.date_from, period.date_to, q.today,
                        tuple(months))


def build_excel(db: Session, q: SectionQuery) -> ObzorExcelOut:
    period, sel = q.period(), q.sel()
    totals = cash.cash_totals(db, sel, period)
    return ObzorExcelOut(
        period=period_out(period), kpis=kpis_out(totals),
        branches=[branch_cash_out(r) for r in cash.by_branch(db, sel, period)],
        total=BranchCashOut(branch_id=0, name="Итого", short_name="Итого", opening=totals.opening,
                            inflow=totals.inflow, outflow=totals.outflow, net=totals.net,
                            closing=totals.closing, diff=totals.diff),
        detail=[DetailRowOut(branch_id=d.branch_id, branch_name=d.branch_name,
                             direction=d.direction, item_id=d.item_id, item_name=d.item_name,
                             activity=d.activity, amount=d.amount)
                for d in cash.detail(db, sel, period)],
    )


def build_item(db: Session, q: SectionQuery, item_id: int) -> ItemBranchesOut:
    period = q.period()
    info, rows = cash.item_branches(db, q.sel(), period, item_id)
    return ItemBranchesOut(
        period=period_out(period),
        item=ItemInfoOut(item_id=info.item_id, code=info.code, name=info.name,
                         activity=info.activity, direction=info.direction),
        total=round(sum(r.fact for r in rows), 2),
        rows=[ItemBranchRowOut(branch_id=r.branch_id, name=r.name, fact=r.fact, plan=r.plan)
              for r in rows])


@router.get("/svod", response_model=ObzorSvodOut)
def svod(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("obzor.svod", q.cache_filters, lambda: build_svod(db, q))


@router.get("/postup", response_model=ObzorFlowOut)
def postup(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("obzor.postup", q.cache_filters, lambda: build_flow(db, q, "in"))


@router.get("/rasxod", response_model=ObzorFlowOut)
def rasxod(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("obzor.rasxod", q.cache_filters, lambda: build_flow(db, q, "out"))


@router.get("/excel", response_model=ObzorExcelOut)
def excel(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("obzor.excel", q.cache_filters, lambda: build_excel(db, q))


@router.get("/items/{item_id}", response_model=ItemBranchesOut)
def item(cache: Cache, db: DB, q: SQ, item_id: Annotated[int, Path(ge=1)]) -> Response:
    return cache.respond("obzor.item", {**q.cache_filters, "item": item_id},
                         lambda: build_item(db, q, item_id))


def _alert_filters(q: SectionQuery, permissions: frozenset[str]) -> dict[str, object]:
    from app.alerts.engine import allowed_sections

    # Natija ruxsatlarga bog'liq — bir xil doiradagi boshqa rol keshini olmasligi uchun.
    return {**q.cache_filters, "sections": allowed_sections(permissions)}


@router.get("/vnimanie", response_model=AlertsOut)
def vnimanie(cache: Cache, db: DB, q: SQ, ctx: Ctx) -> Response:
    from app.alerts.engine import build_alerts

    return cache.respond("obzor.vnimanie", _alert_filters(q, ctx.permissions),
                         lambda: build_alerts(db, q, ctx.permissions))


@router.get("/vnimanie/count", response_model=AlertCountOut)
def vnimanie_count(cache: Cache, db: DB, q: SQ, ctx: Ctx) -> Response:
    from app.alerts.engine import build_count

    return cache.respond("obzor.vnimanie_count", _alert_filters(q, ctx.permissions),
                         lambda: build_count(db, q, ctx.permissions))
