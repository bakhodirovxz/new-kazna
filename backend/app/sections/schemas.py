"""Bo'lim API javoblari (OpenAPI → frontend tiplari). Summalar mln so'm; None — ma'lumot yo'q."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict

from app.sections.period import ReportPeriod
from app.sections.queries.cash import BranchCash, CashTotals, ItemAmount


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReportPeriodOut(_Out):
    code: str
    label: str
    date_from: date
    date_to: date
    open_last: bool


class CashKpisOut(_Out):
    opening: float | None
    inflow: float
    outflow: float
    net: float
    closing: float | None
    diff: float | None
    opening_prev: float | None
    inflow_prev: float
    outflow_prev: float
    net_prev: float
    closing_prev: float | None
    diff_prev: float | None
    has_data: bool


class MonthPointOut(_Out):
    month_id: int
    inflow: float
    outflow: float
    closing: float | None
    inflow_prev: float
    outflow_prev: float


class ItemAmountOut(_Out):
    item_id: int
    code: str
    name: str
    activity: str
    amount: float


class ActivityAmountOut(_Out):
    activity: str
    amount: float


class BranchCashOut(_Out):
    branch_id: int
    name: str
    short_name: str
    opening: float | None
    inflow: float
    outflow: float
    net: float
    closing: float | None
    diff: float | None


class BranchAmountOut(_Out):
    branch_id: int
    name: str
    amount: float


class BankAmountOut(_Out):
    bank_name: str
    amount: float
    closing: float | None


class StationOut(_Out):
    branch_id: int
    code: str
    name: str
    short_name: str
    kind: str
    capacity_mw: float | None
    lat: float | None
    lon: float | None
    inflow: float
    outflow: float
    closing: float | None
    receivable: float | None
    payable: float | None
    overdue_payable: float | None
    # Ishlab chiqarish ko'rsatkichlari (выработка, план, КИУМ) — 3-bosqich rejasi to'ldiradi.
    production: dict[str, float] | None = None


class SeriesOut(_Out):
    key: str
    name: str
    values: list[float]


class DetailRowOut(_Out):
    branch_id: int
    branch_name: str
    direction: str
    item_id: int
    item_name: str
    activity: str
    amount: float


class ItemInfoOut(_Out):
    item_id: int
    code: str
    name: str
    activity: str
    direction: str


class ItemBranchRowOut(_Out):
    branch_id: int
    name: str
    fact: float
    plan: float | None


class ObzorSvodOut(_Out):
    period: ReportPeriodOut
    kpis: CashKpisOut
    months: list[MonthPointOut]
    activity: list[ActivityAmountOut]
    branches: list[BranchCashOut]
    items_in: list[ItemAmountOut]
    items_out: list[ItemAmountOut]
    stations: list[StationOut]


class ObzorFlowOut(_Out):
    period: ReportPeriodOut
    kpis: CashKpisOut
    direction: str
    months: list[int]
    series: list[SeriesOut]
    items: list[ItemAmountOut]
    activity: list[ActivityAmountOut]
    banks: list[BankAmountOut]
    branches: list[BranchAmountOut]


class ObzorExcelOut(_Out):
    period: ReportPeriodOut
    kpis: CashKpisOut
    branches: list[BranchCashOut]
    total: BranchCashOut
    detail: list[DetailRowOut]


class ItemBranchesOut(_Out):
    period: ReportPeriodOut
    item: ItemInfoOut
    total: float
    rows: list[ItemBranchRowOut]


def period_out(p: ReportPeriod) -> ReportPeriodOut:
    return ReportPeriodOut(code=p.code, label=p.label, date_from=p.date_from, date_to=p.date_to,
                           open_last=p.open_last)


def kpis_out(t: CashTotals) -> CashKpisOut:
    return CashKpisOut(
        opening=t.opening, inflow=t.inflow, outflow=t.outflow, net=t.net, closing=t.closing,
        diff=t.diff, opening_prev=t.opening_prev, inflow_prev=t.inflow_prev,
        outflow_prev=t.outflow_prev, net_prev=t.net_prev, closing_prev=t.closing_prev,
        diff_prev=t.diff_prev, has_data=t.has_data)


def branch_cash_out(r: BranchCash) -> BranchCashOut:
    return BranchCashOut(branch_id=r.branch_id, name=r.name, short_name=r.short_name,
                         opening=r.opening, inflow=r.inflow, outflow=r.outflow, net=r.net,
                         closing=r.closing, diff=r.diff)


def items_out(rows: list[ItemAmount]) -> list[ItemAmountOut]:
    return [ItemAmountOut(item_id=i.item_id, code=i.code, name=i.name, activity=i.activity,
                          amount=i.amount) for i in rows]
