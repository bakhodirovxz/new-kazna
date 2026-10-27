"""Ishlab chiqarish (TZ 4 «Производство») — faqat pub.agg_generation_month,
pub.agg_energy_sales_month va pub.branches dan.

YoY (TZ 4): o'tgan yilning yopiq oylari to'liq, davrning ochiq oyiga mos oy — generation_cmp
(1..as_of kunlari). Reja agregatda ochiq oy uchun ulushlangan. Maxraj 0 → None («нет данных»).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dwh.dates import month_id
from app.sections.period import ReportPeriod
from app.sections.queries.cash import num, opt
from app.sections.scope import BranchSel

STATION_KINDS_SQL = "('ges', 'cascade')"
_NONE_MONTH = [0]  # bo'sh ro'yxat o'rniga (ANY('{}') turini PG aniqlay olmaydi)


def _ratio(a: float, b: float) -> float | None:
    return None if b <= 0 else round(a / b, 6)


@dataclass(frozen=True, slots=True)
class GenFigures:
    generation: float
    generation_prev: float
    plan: float
    own_needs: float
    capacity_mw: float | None
    capacity_hours: float
    stations: int
    accrued: float
    paid: float
    branch_id: int = 0
    name: str = ""
    short_name: str = ""

    @property
    def supply(self) -> float:
        """Отпуск в сеть = выработка − собственные нужды (TZ 4)."""
        return round(self.generation - self.own_needs, 3)

    @property
    def execution(self) -> float | None:
        return _ratio(self.generation, self.plan)

    @property
    def kium(self) -> float | None:
        """КИУМ = выработка (mln kVt·soat × 1000 = MVt·soat) / Σ(quvvat × soat)."""
        if self.capacity_hours <= 0:
            return None
        return round(self.generation * 1000 / self.capacity_hours, 6)

    @property
    def own_share(self) -> float | None:
        return _ratio(self.own_needs, self.generation)

    @property
    def payment_level(self) -> float | None:
        return _ratio(self.paid, self.accrued)

    @property
    def has_data(self) -> bool:
        return self.generation > 0 or self.plan > 0 or self.accrued > 0


@dataclass(frozen=True, slots=True)
class GenMonth:
    month_id: int
    generation: float
    plan: float
    generation_prev: float
    accrued: float
    paid: float


_GEN_SUMS = (
    "coalesce(sum(g.generation) FILTER (WHERE g.month_id = ANY(:months)), 0) AS gen, "
    "coalesce(sum(g.generation) FILTER (WHERE g.month_id = ANY(:prev_full)), 0) "
    "+ coalesce(sum(g.generation_cmp) FILTER (WHERE g.month_id = ANY(:prev_cmp)), 0) AS prev, "
    "coalesce(sum(g.plan) FILTER (WHERE g.month_id = ANY(:months)), 0) AS plan, "
    "coalesce(sum(g.own_needs) FILTER (WHERE g.month_id = ANY(:months)), 0) AS own, "
    "coalesce(sum(g.capacity_hours) FILTER (WHERE g.month_id = ANY(:months)), 0) AS ch, "
    "sum(g.capacity_mw) FILTER (WHERE g.month_id = :last) AS cap, "
    "coalesce(sum(g.stations) FILTER (WHERE g.month_id = :last), 0) AS st"
)
_SALES_SUMS = "coalesce(sum(s.accrued), 0) AS acc, coalesce(sum(s.paid), 0) AS paid"


def _bind(period: ReportPeriod) -> dict[str, Any]:
    prev = list(period.prev_months)
    full, cmp = (prev[:-1], prev[-1:]) if period.open_last else (prev, [])
    return {"months": list(period.months), "prev_full": full or _NONE_MONTH,
            "prev_cmp": cmp or _NONE_MONTH, "last": period.last_month,
            "all": [*period.months, *prev]}


def _figures(g: Any, s: Any, **ident: Any) -> GenFigures:
    return GenFigures(
        generation=num(g.gen), generation_prev=num(g.prev), plan=num(g.plan),
        own_needs=num(g.own), capacity_mw=opt(g.cap), capacity_hours=num(g.ch),
        stations=int(g.st), accrued=num(s.acc) if s is not None else 0.0,
        paid=num(s.paid) if s is not None else 0.0, **ident)


def has_stations(db: Session, sel: BranchSel) -> bool:
    where, params = sel.rows("branch_id")
    return bool(db.execute(text(
        f"SELECT EXISTS (SELECT 1 FROM pub.branches WHERE kind IN {STATION_KINDS_SQL} "
        f"AND {where})"), params).scalar_one())


def totals(db: Session, sel: BranchSel, period: ReportPeriod) -> GenFigures:
    bind = _bind(period)
    where, params = sel.total("g.branch_id")
    g = db.execute(text(
        f"SELECT {_GEN_SUMS} FROM pub.agg_generation_month g "
        f"WHERE {where} AND g.month_id = ANY(:all)"), {**params, **bind}).one()
    s_where, s_params = sel.total("s.branch_id")
    s = db.execute(text(
        f"SELECT {_SALES_SUMS} FROM pub.agg_energy_sales_month s "
        f"WHERE {s_where} AND s.month_id = ANY(:months)"),
        {**s_params, "months": bind["months"]}).one()
    return _figures(g, s)


def stations(db: Session, sel: BranchSel, period: ReportPeriod) -> list[GenFigures]:
    bind = _bind(period)
    where, params = sel.rows("g.branch_id")
    rows = db.execute(text(
        f"SELECT g.branch_id, b.name, b.short_name, {_GEN_SUMS} "
        "FROM pub.agg_generation_month g JOIN pub.branches b ON b.branch_id = g.branch_id "
        f"WHERE {where} AND b.kind IN {STATION_KINDS_SQL} AND g.month_id = ANY(:all) "
        "GROUP BY g.branch_id, b.name, b.short_name, b.sort_order "
        "ORDER BY b.sort_order, g.branch_id"), {**params, **bind}).all()
    s_where, s_params = sel.rows("s.branch_id")
    sales = {int(r.branch_id): r for r in db.execute(text(
        f"SELECT s.branch_id, {_SALES_SUMS} FROM pub.agg_energy_sales_month s "
        f"WHERE {s_where} AND s.month_id = ANY(:months) GROUP BY s.branch_id"),
        {**s_params, "months": bind["months"]}).all()}
    return [_figures(r, sales.get(int(r.branch_id)), branch_id=int(r.branch_id), name=r.name,
                     short_name=r.short_name) for r in rows]


def station_map(db: Session, sel: BranchSel, period: ReportPeriod) -> dict[int, GenFigures]:
    return {s.branch_id: s for s in stations(db, sel, period)}


def monthly(db: Session, sel: BranchSel, today: date) -> list[GenMonth]:
    """Joriy yil yanvaridan joriy oygacha; o'tgan yil — joriy oy uchun shuncha kun."""
    current = month_id(today)
    months = [today.year * 100 + m for m in range(1, today.month + 1)]
    where, params = sel.total("g.branch_id")
    gen = {int(r.month_id): r for r in db.execute(text(
        "SELECT g.month_id, sum(g.generation) AS gen, sum(g.generation_cmp) AS cmp, "
        "sum(g.plan) AS plan FROM pub.agg_generation_month g "
        f"WHERE {where} AND g.month_id = ANY(:m) GROUP BY g.month_id"),
        {**params, "m": months + [m - 100 for m in months]}).all()}
    s_where, s_params = sel.total("s.branch_id")
    sales = {int(r.month_id): r for r in db.execute(text(
        f"SELECT s.month_id, {_SALES_SUMS} FROM pub.agg_energy_sales_month s "
        f"WHERE {s_where} AND s.month_id = ANY(:m) GROUP BY s.month_id"),
        {**s_params, "m": months}).all()}
    out: list[GenMonth] = []
    for m in months:
        cur, prev, sale = gen.get(m), gen.get(m - 100), sales.get(m)
        prev_value = 0.0
        if prev is not None:
            prev_value = num(prev.cmp if m == current else prev.gen)
        out.append(GenMonth(
            month_id=m, generation=num(cur.gen) if cur else 0.0,
            plan=num(cur.plan) if cur else 0.0, generation_prev=prev_value,
            accrued=num(sale.acc) if sale else 0.0, paid=num(sale.paid) if sale else 0.0))
    return out
