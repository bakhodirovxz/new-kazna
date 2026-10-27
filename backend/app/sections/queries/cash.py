"""Pul oqimlari ko'rsatkichlari (TZ 4 «Денежные средства»/«Казначейство») — faqat pub view'lardan.

Ustun va shart fragmentlari faqat shu fayldagi konstantalar va BranchSel'dan (whitelist).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.dwh.dates import month_id
from app.sections.period import ReportPeriod
from app.sections.scope import BranchSel

ACTIVITIES = ("centralized", "operating", "investing")
_FLOW_COL = {"in": "inflow", "out": "outflow"}


def num(value: Decimal | float | int | None) -> float:
    return 0.0 if value is None else float(value)


def opt(value: Decimal | float | int | None) -> float | None:
    return None if value is None else float(value)


def _diff(opening: float | None, net: float, closing: float | None) -> float | None:
    if opening is None or closing is None:
        return None
    return round(closing - (opening + net), 2)


@dataclass(frozen=True, slots=True)
class CashTotals:
    opening: float | None
    inflow: float
    outflow: float
    closing: float | None
    opening_prev: float | None
    inflow_prev: float
    outflow_prev: float
    closing_prev: float | None
    has_data: bool

    @property
    def net(self) -> float:
        return round(self.inflow - self.outflow, 2)

    @property
    def diff(self) -> float | None:
        return _diff(self.opening, self.net, self.closing)

    @property
    def net_prev(self) -> float:
        return round(self.inflow_prev - self.outflow_prev, 2)

    @property
    def diff_prev(self) -> float | None:
        return _diff(self.opening_prev, self.net_prev, self.closing_prev)


@dataclass(frozen=True, slots=True)
class MonthPoint:
    month_id: int
    inflow: float
    outflow: float
    closing: float | None
    inflow_prev: float
    outflow_prev: float


@dataclass(frozen=True, slots=True)
class ItemAmount:
    item_id: int
    code: str
    name: str
    activity: str
    amount: float


@dataclass(frozen=True, slots=True)
class ActivityAmount:
    activity: str
    amount: float


@dataclass(frozen=True, slots=True)
class BranchCash:
    branch_id: int
    name: str
    short_name: str
    opening: float | None
    inflow: float
    outflow: float
    closing: float | None

    @property
    def net(self) -> float:
        return round(self.inflow - self.outflow, 2)

    @property
    def diff(self) -> float | None:
        return _diff(self.opening, self.net, self.closing)


@dataclass(frozen=True, slots=True)
class BankAmount:
    bank_name: str
    inflow: float
    outflow: float
    closing: float | None


@dataclass(frozen=True, slots=True)
class ItemInfo:
    item_id: int
    code: str
    name: str
    activity: str
    direction: str


@dataclass(frozen=True, slots=True)
class ItemBranchRow:
    branch_id: int
    name: str
    fact: float
    plan: float | None


@dataclass(frozen=True, slots=True)
class DetailRow:
    branch_id: int
    branch_name: str
    direction: str
    item_id: int
    item_name: str
    activity: str
    amount: float


def _month_rows(db: Session, sel: BranchSel, months: list[int]) -> dict[int, Any]:
    where, params = sel.total()
    rows = db.execute(text(
        "SELECT month_id, sum(inflow) AS i, sum(outflow) AS o, sum(inflow_cmp) AS ic, "
        "sum(outflow_cmp) AS oc, sum(opening_balance) AS ob, sum(closing_balance) AS cb "
        f"FROM pub.agg_cash_month WHERE item_id = 0 AND {where} AND month_id = ANY(:months) "
        "GROUP BY month_id"), {**params, "months": months}).all()
    return {int(r.month_id): r for r in rows}


def _sum(by: dict[int, Any], months: tuple[int, ...] | list[int], attr: str) -> float:
    return round(sum(num(getattr(by[m], attr)) for m in months if m in by), 2)


def _closing_cmp(db: Session, sel: BranchSel, month: int) -> float | None:
    where, params = sel.total()
    return opt(db.execute(text(
        f"SELECT sum(closing_cmp) FROM pub.agg_cash_bank_month WHERE {where} AND month_id = :m"),
        {**params, "m": month}).scalar_one())


def cash_totals(db: Session, sel: BranchSel, period: ReportPeriod) -> CashTotals:
    prev = period.prev_months
    by = _month_rows(db, sel, [*period.months, *prev])
    if period.open_last:
        inflow_prev = _sum(by, prev[:-1], "i") + _sum(by, prev[-1:], "ic")
        outflow_prev = _sum(by, prev[:-1], "o") + _sum(by, prev[-1:], "oc")
        closing_prev = _closing_cmp(db, sel, prev[-1])
    else:
        inflow_prev = _sum(by, prev, "i")
        outflow_prev = _sum(by, prev, "o")
        closing_prev = opt(by[prev[-1]].cb) if prev[-1] in by else None
    first, last = period.first_month, period.last_month
    return CashTotals(
        opening=opt(by[first].ob) if first in by else None,
        inflow=_sum(by, period.months, "i"),
        outflow=_sum(by, period.months, "o"),
        closing=opt(by[last].cb) if last in by else None,
        opening_prev=opt(by[prev[0]].ob) if prev[0] in by else None,
        inflow_prev=round(inflow_prev, 2),
        outflow_prev=round(outflow_prev, 2),
        closing_prev=closing_prev,
        has_data=any(m in by for m in period.months),
    )


def monthly(db: Session, sel: BranchSel, today: date) -> list[MonthPoint]:
    """Joriy yil yanvaridan joriy oygacha + o'tgan yilning o'sha oylari (joriy oy — shuncha kun)."""
    current = month_id(today)
    months = [today.year * 100 + m for m in range(1, today.month + 1)]
    by = _month_rows(db, sel, months + [m - 100 for m in months])
    out: list[MonthPoint] = []
    for m in months:
        prev = by.get(m - 100)
        cur = by.get(m)
        cmp = m == current
        out.append(MonthPoint(
            month_id=m,
            inflow=num(cur.i) if cur else 0.0,
            outflow=num(cur.o) if cur else 0.0,
            closing=opt(cur.cb) if cur else None,
            inflow_prev=num(prev.ic if cmp else prev.i) if prev else 0.0,
            outflow_prev=num(prev.oc if cmp else prev.o) if prev else 0.0,
        ))
    return out


def items(db: Session, sel: BranchSel, period: ReportPeriod, direction: str) -> list[ItemAmount]:
    col = _FLOW_COL[direction]
    where, params = sel.total("a.branch_id")
    rows = db.execute(text(
        f"SELECT a.item_id, i.code, i.name, i.activity, sum(a.{col}) AS amount "
        "FROM pub.agg_cash_month a JOIN pub.items i ON i.item_id = a.item_id "
        f"WHERE a.item_id <> 0 AND i.direction = :dir AND {where} AND a.month_id = ANY(:months) "
        f"GROUP BY a.item_id, i.code, i.name, i.activity HAVING sum(a.{col}) > 0 "
        "ORDER BY amount DESC, i.name"),
        {**params, "dir": direction, "months": list(period.months)}).all()
    return [ItemAmount(int(r.item_id), r.code, r.name, r.activity, num(r.amount)) for r in rows]


def activity_split(items_out: list[ItemAmount]) -> list[ActivityAmount]:
    totals = dict.fromkeys(ACTIVITIES, 0.0)
    for item in items_out:
        totals[item.activity] = round(totals[item.activity] + item.amount, 2)
    return [ActivityAmount(a, totals[a]) for a in ACTIVITIES]


def by_branch(db: Session, sel: BranchSel, period: ReportPeriod) -> list[BranchCash]:
    where, params = sel.rows("a.branch_id")
    rows = db.execute(text(
        "SELECT a.branch_id, b.name, b.short_name, sum(a.inflow) AS i, sum(a.outflow) AS o, "
        "sum(a.opening_balance) FILTER (WHERE a.month_id = :first) AS ob, "
        "sum(a.closing_balance) FILTER (WHERE a.month_id = :last) AS cb "
        "FROM pub.agg_cash_month a JOIN pub.branches b ON b.branch_id = a.branch_id "
        f"WHERE a.item_id = 0 AND {where} AND a.month_id = ANY(:months) "
        "GROUP BY a.branch_id, b.name, b.short_name, b.sort_order "
        "ORDER BY b.sort_order, a.branch_id"),
        {**params, "months": list(period.months), "first": period.first_month,
         "last": period.last_month}).all()
    return [BranchCash(int(r.branch_id), r.name, r.short_name, opt(r.ob), num(r.i), num(r.o),
                       opt(r.cb)) for r in rows]


def banks(db: Session, sel: BranchSel, period: ReportPeriod) -> list[BankAmount]:
    where, params = sel.total()
    rows = db.execute(text(
        "SELECT bank_name, sum(inflow) AS i, sum(outflow) AS o, "
        "sum(closing_balance) FILTER (WHERE month_id = :last) AS cb "
        f"FROM pub.agg_cash_bank_month WHERE {where} AND month_id = ANY(:months) "
        "GROUP BY bank_name ORDER BY bank_name"),
        {**params, "months": list(period.months), "last": period.last_month}).all()
    return [BankAmount(r.bank_name, num(r.i), num(r.o), opt(r.cb)) for r in rows]


def item_info(db: Session, item_id: int) -> ItemInfo:
    row = db.execute(text("SELECT item_id, code, name, activity, direction FROM pub.items "
                          "WHERE item_id = :i"), {"i": item_id}).one_or_none()
    if row is None:
        raise NotFoundError()
    return ItemInfo(int(row.item_id), row.code, row.name, row.activity, row.direction)


def item_branches(db: Session, sel: BranchSel, period: ReportPeriod,
                  item_id: int) -> tuple[ItemInfo, list[ItemBranchRow]]:
    info = item_info(db, item_id)
    col = _FLOW_COL[info.direction]
    where, params = sel.rows("a.branch_id")
    bind = {**params, "i": item_id, "months": list(period.months)}
    facts = {int(r.branch_id): (r.name, num(r.v)) for r in db.execute(text(
        f"SELECT a.branch_id, b.name, sum(a.{col}) AS v FROM pub.agg_cash_month a "
        "JOIN pub.branches b ON b.branch_id = a.branch_id "
        f"WHERE a.item_id = :i AND {where} AND a.month_id = ANY(:months) "
        "GROUP BY a.branch_id, b.name"), bind).all()}
    plans: dict[int, tuple[str, float]] = {}
    if info.direction == "out":
        plans = {int(r.branch_id): (r.name, num(r.v)) for r in db.execute(text(
            "SELECT a.branch_id, b.name, sum(a.plan_amount) AS v FROM pub.agg_payments_month a "
            "JOIN pub.branches b ON b.branch_id = a.branch_id "
            f"WHERE a.item_id = :i AND {where} AND a.month_id = ANY(:months) "
            "GROUP BY a.branch_id, b.name"), bind).all()}
    rows: list[ItemBranchRow] = []
    for branch_id in set(facts) | set(plans):
        name = (facts.get(branch_id) or plans[branch_id])[0]
        fact = facts[branch_id][1] if branch_id in facts else 0.0
        plan = plans[branch_id][1] if branch_id in plans else (0.0 if plans else None)
        if info.direction == "in":
            plan = None
        if fact > 0 or (plan or 0) > 0:
            rows.append(ItemBranchRow(branch_id, name, fact, plan))
    rows.sort(key=lambda r: (-r.fact, r.name))
    return info, rows


def detail(db: Session, sel: BranchSel, period: ReportPeriod) -> list[DetailRow]:
    where, params = sel.rows("a.branch_id")
    rows = db.execute(text(
        "SELECT a.branch_id, b.name AS branch_name, i.direction, i.item_id, i.name AS item_name, "
        "i.activity, sum(CASE WHEN i.direction = 'in' THEN a.inflow ELSE a.outflow END) AS amount "
        "FROM pub.agg_cash_month a JOIN pub.items i ON i.item_id = a.item_id "
        "JOIN pub.branches b ON b.branch_id = a.branch_id "
        f"WHERE a.item_id <> 0 AND {where} AND a.month_id = ANY(:months) "
        "GROUP BY a.branch_id, b.name, b.sort_order, i.direction, i.item_id, i.name, i.activity "
        "HAVING sum(CASE WHEN i.direction = 'in' THEN a.inflow ELSE a.outflow END) > 0 "
        "ORDER BY b.sort_order, a.branch_id, i.direction, amount DESC"),
        {**params, "months": list(period.months)}).all()
    return [DetailRow(int(r.branch_id), r.branch_name, r.direction, int(r.item_id), r.item_name,
                      r.activity, num(r.amount)) for r in rows]
