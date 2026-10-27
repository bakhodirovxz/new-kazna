"""Ombor (TZ 4 «Склад») — faqat pub.agg_stock_month, pub.agg_stock_positions va pub.branches dan.

Qiymat, minimum, неликвид va yosh — davr oxirgi oyining snapshot'idan; prixod/rasxod — davr
oylari yig'indisi; оборачиваемость = qiymat / (rasxod / davr kunlari), kunlarda.
Minimum yoki oxirgi harakat sanasi manbada yo'q bo'lsa — tegishli ko'rsatkich None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dwh.dates import from_date_id, month_id
from app.sections.period import ReportPeriod
from app.sections.queries.cash import num
from app.sections.scope import BranchSel

AGE_KEYS = ("le90", "d91_180", "d181_365", "gt365", "unknown")
_AGE_COLS = {"le90": "age_le90", "d91_180": "age_91_180", "d181_365": "age_181_365",
             "gt365": "age_gt365", "unknown": "age_unknown"}
POSITIONS_LIMIT = 500


@dataclass(frozen=True, slots=True)
class StockFigures:
    as_of: date
    value: float
    positions: int
    below_min: int
    min_known: int
    idle_value: float
    age_known_value: float
    inflow: float
    outflow: float
    days: int

    @property
    def turnover_days(self) -> float | None:
        """Оборачиваемость = стоимость запасов / (расход за период / число дней)."""
        if self.outflow <= 0 or self.days <= 0:
            return None
        return round(self.value / (self.outflow / self.days), 1)

    @property
    def idle_share(self) -> float | None:
        if self.value <= 0 or self.age_known_value <= 0:
            return None
        return round(self.idle_value / self.value, 6)

    @property
    def has_data(self) -> bool:
        return self.positions > 0 or self.inflow > 0 or self.outflow > 0

    @property
    def has_minimum(self) -> bool:
        return self.min_known > 0

    @property
    def has_age(self) -> bool:
        return self.age_known_value > 0


@dataclass(frozen=True, slots=True)
class NamedValue:
    name: str
    value: float


@dataclass(frozen=True, slots=True)
class AgeBucket:
    key: str
    value: float


@dataclass(frozen=True, slots=True)
class StockBranch:
    branch_id: int
    name: str
    value: float
    positions: int
    below_min: int
    idle_value: float


@dataclass(frozen=True, slots=True)
class StockPosition:
    branch_id: int
    branch_name: str
    warehouse: str
    nom_code: str
    name: str
    category: str
    unit: str
    qty: float
    min_qty: float | None
    value: float
    age_days: int | None

    @property
    def coverage(self) -> float | None:
        """Обеспеченность = количество / минимум."""
        if self.min_qty is None or self.min_qty <= 0:
            return None
        return round(self.qty / self.min_qty, 6)


@dataclass(frozen=True, slots=True)
class StockMonth:
    month_id: int
    inflow: float
    outflow: float


def totals(db: Session, sel: BranchSel, period: ReportPeriod) -> StockFigures:
    where, params = sel.total("a.branch_id")
    snap = db.execute(text(
        "SELECT max(a.snap_date_id) AS snap, coalesce(sum(a.positions), 0) AS pos, "
        "coalesce(sum(a.value), 0) AS value, coalesce(sum(a.below_min), 0) AS below, "
        "coalesce(sum(a.min_known), 0) AS known, coalesce(sum(a.idle_value), 0) AS idle, "
        "coalesce(sum(a.age_le90 + a.age_91_180 + a.age_181_365 + a.age_gt365), 0) AS aged "
        f"FROM pub.agg_stock_month a WHERE {where} AND a.month_id = :last"),
        {**params, "last": period.last_month}).one()
    flow = db.execute(text(
        "SELECT coalesce(sum(a.inflow), 0) AS i, coalesce(sum(a.outflow), 0) AS o "
        f"FROM pub.agg_stock_month a WHERE {where} AND a.month_id = ANY(:months)"),
        {**params, "months": list(period.months)}).one()
    as_of = from_date_id(int(snap.snap)) if snap.snap is not None else period.date_to
    return StockFigures(
        as_of=as_of, value=num(snap.value), positions=int(snap.pos), below_min=int(snap.below),
        min_known=int(snap.known), idle_value=num(snap.idle), age_known_value=num(snap.aged),
        inflow=num(flow.i), outflow=num(flow.o),
        days=(period.date_to - period.date_from).days + 1)


def categories(db: Session, sel: BranchSel, month: int) -> list[NamedValue]:
    where, params = sel.total("a.branch_id")
    rows = db.execute(text(
        "SELECT a.category, sum(a.value) AS v FROM pub.agg_stock_month a "
        f"WHERE {where} AND a.month_id = :m GROUP BY a.category HAVING sum(a.value) > 0 "
        "ORDER BY v DESC, a.category"), {**params, "m": month}).all()
    return [NamedValue(r.category, num(r.v)) for r in rows]


def ages(db: Session, sel: BranchSel, month: int) -> list[AgeBucket]:
    where, params = sel.total("a.branch_id")
    cols = ", ".join(f"coalesce(sum(a.{col}), 0) AS {key}" for key, col in _AGE_COLS.items())
    row = db.execute(text(f"SELECT {cols} FROM pub.agg_stock_month a "
                          f"WHERE {where} AND a.month_id = :m"), {**params, "m": month}).one()
    return [AgeBucket(key, num(getattr(row, key))) for key in AGE_KEYS]


def by_branch(db: Session, sel: BranchSel, period: ReportPeriod) -> list[StockBranch]:
    where, params = sel.rows("a.branch_id")
    rows = db.execute(text(
        "SELECT a.branch_id, b.name, sum(a.value) AS v, sum(a.positions) AS pos, "
        "sum(a.below_min) AS below, sum(a.idle_value) AS idle "
        "FROM pub.agg_stock_month a JOIN pub.branches b ON b.branch_id = a.branch_id "
        f"WHERE {where} AND a.month_id = :m GROUP BY a.branch_id, b.name "
        "HAVING sum(a.positions) > 0 ORDER BY v DESC, b.name"),
        {**params, "m": period.last_month}).all()
    return [StockBranch(int(r.branch_id), r.name, num(r.v), int(r.pos), int(r.below),
                        num(r.idle)) for r in rows]


_ORDER = {"below": "p.qty / nullif(p.min_qty, 0), p.value DESC, p.name",
          "idle": "p.value DESC, p.name"}


def positions(db: Session, sel: BranchSel, month: int, kind: Literal["below", "idle"],
              limit: int = POSITIONS_LIMIT) -> list[StockPosition]:
    where, params = sel.rows("p.branch_id")
    flag = "p.below_min" if kind == "below" else "p.idle"
    rows = db.execute(text(
        "SELECT p.branch_id, b.name AS branch_name, p.warehouse, p.nom_code, p.name, p.category, "
        "p.unit, p.qty, p.min_qty, p.value, p.age_days "
        "FROM pub.agg_stock_positions p JOIN pub.branches b ON b.branch_id = p.branch_id "
        f"WHERE {where} AND p.month_id = :m AND {flag} ORDER BY {_ORDER[kind]} LIMIT :limit"),
        {**params, "m": month, "limit": limit}).all()
    return [_position(r) for r in rows]


def _position(r: Any) -> StockPosition:
    return StockPosition(
        branch_id=int(r.branch_id), branch_name=r.branch_name, warehouse=r.warehouse,
        nom_code=r.nom_code, name=r.name, category=r.category, unit=r.unit, qty=num(r.qty),
        min_qty=None if r.min_qty is None else num(r.min_qty), value=num(r.value),
        age_days=None if r.age_days is None else int(r.age_days))


def flows(db: Session, sel: BranchSel, today: date) -> list[StockMonth]:
    months = [today.year * 100 + m for m in range(1, month_id(today) % 100 + 1)]
    where, params = sel.total("a.branch_id")
    by = {int(r.month_id): r for r in db.execute(text(
        "SELECT a.month_id, sum(a.inflow) AS i, sum(a.outflow) AS o FROM pub.agg_stock_month a "
        f"WHERE {where} AND a.month_id = ANY(:m) GROUP BY a.month_id"),
        {**params, "m": months}).all()}
    return [StockMonth(m, num(by[m].i) if m in by else 0.0, num(by[m].o) if m in by else 0.0)
            for m in months]
