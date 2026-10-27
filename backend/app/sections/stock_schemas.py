"""«Склад» API javoblari. Qiymatlar mln so'm, oborot — kunlarda, ulushlar 0..1;
has_minimum / has_age = false — manbada minimum yoki oxirgi harakat sanasi yo'q
(UI «Источник не подключён»)."""

from __future__ import annotations

from datetime import date

from app.sections.queries.stock import NamedValue, StockFigures, StockPosition
from app.sections.schemas import ReportPeriodOut, _Out


class NamedAmountOut(_Out):
    name: str
    amount: float


class StockKpisOut(_Out):
    as_of: date
    has_data: bool
    value: float
    turnover_days: float | None
    positions: int
    below_min: int
    has_minimum: bool
    idle_value: float
    idle_share: float | None
    has_age: bool
    inflow: float
    outflow: float


class StockMonthOut(_Out):
    month_id: int
    inflow: float
    outflow: float


class StockBranchOut(_Out):
    branch_id: int
    name: str
    value: float
    positions: int
    below_min: int
    idle_value: float


class StockPositionOut(_Out):
    branch_id: int
    branch_name: str
    warehouse: str
    nom_code: str
    name: str
    category: str
    unit: str
    qty: float
    min_qty: float | None
    coverage: float | None
    value: float
    age_days: int | None


class AgeBucketOut(_Out):
    key: str
    value: float


class SkladSvodOut(_Out):
    period: ReportPeriodOut
    kpis: StockKpisOut
    months: list[StockMonthOut]
    categories: list[NamedAmountOut]
    below: list[StockPositionOut]


class SkladOstatkiOut(_Out):
    period: ReportPeriodOut
    kpis: StockKpisOut
    branches: list[StockBranchOut]
    categories: list[NamedAmountOut]


class SkladMinimumOut(_Out):
    period: ReportPeriodOut
    kpis: StockKpisOut
    below: list[StockPositionOut]


class SkladNelikvidOut(_Out):
    period: ReportPeriodOut
    kpis: StockKpisOut
    ages: list[AgeBucketOut]
    illiquid: list[StockPositionOut]


def stock_kpis_out(t: StockFigures) -> StockKpisOut:
    return StockKpisOut(
        as_of=t.as_of, has_data=t.has_data, value=t.value, turnover_days=t.turnover_days,
        positions=t.positions, below_min=t.below_min, has_minimum=t.has_minimum,
        idle_value=t.idle_value, idle_share=t.idle_share, has_age=t.has_age, inflow=t.inflow,
        outflow=t.outflow)


def position_out(p: StockPosition) -> StockPositionOut:
    return StockPositionOut(
        branch_id=p.branch_id, branch_name=p.branch_name, warehouse=p.warehouse,
        nom_code=p.nom_code, name=p.name, category=p.category, unit=p.unit, qty=p.qty,
        min_qty=p.min_qty, coverage=p.coverage, value=p.value, age_days=p.age_days)


def named_values_out(items: list[NamedValue]) -> list[NamedAmountOut]:
    return [NamedAmountOut(name=i.name, amount=i.value) for i in items]
