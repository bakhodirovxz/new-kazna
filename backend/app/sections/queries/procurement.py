"""Xaridlar (TZ 4 «Закупки») — faqat pub.agg_procurement_lots, pub.agg_procurement_plan va
pub.branches dan.

Davr ko'rsatkichlari — sanasi davr oylariga tushgan tuzilgan/bekor qilingan lotlar; «в работе» va
«просроченные» — joriy holat, davr oxirigacha e'lon qilinganlar (S4 spec 11.2). Yillik reja
bajarilishi — davr yili 1-yanvaridan davr oxirigacha tuzilgan shartnomalar / yillik reja.
Maxraj 0 → None («нет данных»).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dwh.dates import date_id, month_id
from app.etl.zakupki.codes import CANCELLED, DIRECT, DONE, IN_WORK, METHOD_TITLES, METHODS
from app.sections.period import ReportPeriod
from app.sections.queries.cash import num
from app.sections.scope import BranchSel

LOTS_LIMIT = 1000
_IN_WORK = ", ".join(f"'{s}'" for s in IN_WORK)  # kod konstantalari — whitelist
_DONE = "l.status = :done"
_PERIOD = "l.month_id = ANY(:months)"


def pairs(result: Any) -> dict[Any, Any]:
    """(kalit, qiymat) qatorlaridan lug'at (mypy: Row[Any] -> tuple)."""
    return {r[0]: r[1] for r in result}


def ratio(a: float, b: float) -> float | None:
    return None if b <= 0 else round(a / b, 6)


@dataclass(frozen=True, slots=True)
class ProcFigures:
    contracted: float
    contracts: int
    start_contracted: float
    direct: float
    days_sum: float
    days_n: int
    ytd: float
    plan: float
    in_work: int
    in_work_start: float
    overdue: int
    overdue_start: float
    cancelled: int
    cancelled_start: float

    @property
    def savings(self) -> float:
        """Экономия = начальная цена − цена договора (TZ 4)."""
        return round(self.start_contracted - self.contracted, 2)

    @property
    def savings_share(self) -> float | None:
        return ratio(self.savings, self.start_contracted)

    @property
    def plan_execution(self) -> float | None:
        return ratio(self.ytd, self.plan)

    @property
    def direct_share(self) -> float | None:
        return ratio(self.direct, self.contracted)

    @property
    def avg_days(self) -> float | None:
        return None if self.days_n <= 0 else round(self.days_sum / self.days_n, 1)

    @property
    def has_data(self) -> bool:
        return self.contracts > 0 or self.in_work > 0 or self.plan > 0 or self.cancelled > 0


@dataclass(frozen=True, slots=True)
class ProcMonth:
    month_id: int
    contracted: float


@dataclass(frozen=True, slots=True)
class MethodRow:
    method: str
    title: str
    lots: int
    start: float
    contracted: float
    days_sum: float
    days_n: int
    norm_days: int | None

    @property
    def savings(self) -> float:
        return round(self.start - self.contracted, 2)

    @property
    def savings_share(self) -> float | None:
        return ratio(self.savings, self.start)

    @property
    def avg_days(self) -> float | None:
        return None if self.days_n <= 0 else round(self.days_sum / self.days_n, 1)


@dataclass(frozen=True, slots=True)
class LotRow:
    lot_no: str
    branch_id: int
    branch_name: str
    date_id: int
    method: str
    method_title: str
    subject: str
    status: str
    start_price: float
    contract_price: float | None
    days: int | None
    norm_days: int | None
    overdue: bool
    supplier: str | None

    @property
    def kind(self) -> str:
        if self.status == DONE:
            return "done"
        return "cancelled" if self.status == CANCELLED else "work"


@dataclass(frozen=True, slots=True)
class NamedCount:
    name: str
    amount: float
    count: int


@dataclass(frozen=True, slots=True)
class ProcBranch:
    branch_id: int
    name: str
    plan: float
    ytd: float
    savings: float

    @property
    def execution(self) -> float | None:
        return ratio(self.ytd, self.plan)


def _ytd(period: ReportPeriod) -> list[int]:
    year = period.last_month // 100
    return [year * 100 + m for m in range(1, period.last_month % 100 + 1)]


def _bind(period: ReportPeriod) -> dict[str, Any]:
    return {"months": list(period.months), "ytd": _ytd(period), "end_id": date_id(period.date_to),
            "done": DONE, "cancelled": CANCELLED, "direct": DIRECT}


def totals(db: Session, sel: BranchSel, period: ReportPeriod) -> ProcFigures:
    where, params = sel.rows("l.branch_id")
    work = f"l.status IN ({_IN_WORK}) AND l.date_id <= :end_id"
    r = db.execute(text(
        "SELECT "
        f"coalesce(sum(l.contract_price) FILTER (WHERE {_DONE} AND {_PERIOD}), 0) AS contracted, "
        f"count(*) FILTER (WHERE {_DONE} AND {_PERIOD}) AS contracts, "
        f"coalesce(sum(l.start_price) FILTER (WHERE {_DONE} AND {_PERIOD}), 0) AS start_c, "
        f"coalesce(sum(l.contract_price) FILTER (WHERE {_DONE} AND {_PERIOD} "
        "AND l.method = :direct), 0) AS direct, "
        f"coalesce(sum(l.days) FILTER (WHERE {_DONE} AND {_PERIOD}), 0) AS days_sum, "
        f"count(l.days) FILTER (WHERE {_DONE} AND {_PERIOD}) AS days_n, "
        f"coalesce(sum(l.contract_price) FILTER (WHERE {_DONE} AND l.month_id = ANY(:ytd)), 0) "
        "AS ytd, "
        f"count(*) FILTER (WHERE {work}) AS in_work, "
        f"coalesce(sum(l.start_price) FILTER (WHERE {work}), 0) AS in_work_start, "
        "count(*) FILTER (WHERE l.overdue AND l.date_id <= :end_id) AS overdue, "
        "coalesce(sum(l.start_price) FILTER (WHERE l.overdue AND l.date_id <= :end_id), 0) "
        "AS overdue_start, "
        f"count(*) FILTER (WHERE l.status = :cancelled AND {_PERIOD}) AS cancelled, "
        f"coalesce(sum(l.start_price) FILTER (WHERE l.status = :cancelled AND {_PERIOD}), 0) "
        "AS cancelled_start "
        f"FROM pub.agg_procurement_lots l WHERE {where}"), {**params, **_bind(period)}).one()
    p_where, p_params = sel.total("p.branch_id")
    plan = db.execute(text(
        f"SELECT coalesce(sum(p.plan), 0) FROM pub.agg_procurement_plan p WHERE {p_where} "
        "AND p.month_id = :year01"),
        {**p_params, "year01": period.last_month // 100 * 100 + 1}).scalar_one()
    return ProcFigures(
        contracted=num(r.contracted), contracts=int(r.contracts), start_contracted=num(r.start_c),
        direct=num(r.direct), days_sum=num(r.days_sum), days_n=int(r.days_n), ytd=num(r.ytd),
        plan=num(plan), in_work=int(r.in_work), in_work_start=num(r.in_work_start),
        overdue=int(r.overdue), overdue_start=num(r.overdue_start), cancelled=int(r.cancelled),
        cancelled_start=num(r.cancelled_start))


def monthly(db: Session, sel: BranchSel, today: date) -> list[ProcMonth]:
    months = [today.year * 100 + m for m in range(1, month_id(today) % 100 + 1)]
    where, params = sel.rows("l.branch_id")
    by = pairs(db.execute(text(
        "SELECT l.month_id, sum(l.contract_price) FROM pub.agg_procurement_lots l "
        f"WHERE {where} AND {_DONE} AND l.month_id = ANY(:months) GROUP BY l.month_id"),
        {**params, "months": months, "done": DONE}).all())
    return [ProcMonth(m, num(by.get(m))) for m in months]


def by_method(db: Session, sel: BranchSel, period: ReportPeriod) -> list[MethodRow]:
    where, params = sel.rows("l.branch_id")
    rows = db.execute(text(
        "SELECT l.method, count(*) AS n, sum(l.start_price) AS s, sum(l.contract_price) AS c, "
        "coalesce(sum(l.days), 0) AS ds, count(l.days) AS dn, max(l.norm_days) AS norm "
        f"FROM pub.agg_procurement_lots l WHERE {where} AND {_DONE} AND {_PERIOD} "
        "GROUP BY l.method ORDER BY c DESC, l.method"), {**params, **_bind(period)}).all()
    return [MethodRow(r.method, METHOD_TITLES.get(r.method, r.method), int(r.n), num(r.s),
                      num(r.c), num(r.ds), int(r.dn),
                      None if r.norm is None else int(r.norm)) for r in rows
            if r.method in METHODS]


_LOT_COLS = ("l.lot_no, l.branch_id, b.name AS branch_name, l.date_id, l.method, l.subject, "
             "l.status, l.start_price, l.contract_price, l.days, l.norm_days, l.overdue, "
             "l.supplier")


def _lot(r: Any) -> LotRow:
    return LotRow(
        lot_no=r.lot_no, branch_id=int(r.branch_id), branch_name=r.branch_name,
        date_id=int(r.date_id), method=r.method,
        method_title=METHOD_TITLES.get(r.method, r.method), subject=r.subject, status=r.status,
        start_price=num(r.start_price),
        contract_price=None if r.contract_price is None else num(r.contract_price),
        days=None if r.days is None else int(r.days),
        norm_days=None if r.norm_days is None else int(r.norm_days), overdue=bool(r.overdue),
        supplier=r.supplier)


def lots(db: Session, sel: BranchSel, period: ReportPeriod,
         limit: int = LOTS_LIMIT) -> list[LotRow]:
    where, params = sel.rows("l.branch_id")
    rows = db.execute(text(
        f"SELECT {_LOT_COLS} FROM pub.agg_procurement_lots l "
        "JOIN pub.branches b ON b.branch_id = l.branch_id "
        f"WHERE {where} AND ((l.status IN (:done, :cancelled) AND {_PERIOD}) "
        f"OR (l.status IN ({_IN_WORK}) AND l.date_id <= :end_id)) "
        "ORDER BY l.overdue DESC, l.start_price DESC, l.lot_no LIMIT :limit"),
        {**params, **_bind(period), "limit": limit}).all()
    return [_lot(r) for r in rows]


def cancelled(db: Session, sel: BranchSel, period: ReportPeriod) -> list[LotRow]:
    where, params = sel.rows("l.branch_id")
    rows = db.execute(text(
        f"SELECT {_LOT_COLS} FROM pub.agg_procurement_lots l "
        "JOIN pub.branches b ON b.branch_id = l.branch_id "
        f"WHERE {where} AND l.status = :cancelled AND {_PERIOD} "
        "ORDER BY l.start_price DESC, l.lot_no LIMIT :limit"),
        {**params, **_bind(period), "limit": LOTS_LIMIT}).all()
    return [_lot(r) for r in rows]


def _grouped(db: Session, sel: BranchSel, period: ReportPeriod, column: str) -> list[NamedCount]:
    where, params = sel.rows("l.branch_id")
    rows = db.execute(text(
        f"SELECT coalesce(l.{column}, '—') AS name, sum(l.contract_price) AS a, count(*) AS n "
        f"FROM pub.agg_procurement_lots l WHERE {where} AND {_DONE} AND {_PERIOD} "
        "GROUP BY 1 ORDER BY a DESC, name"), {**params, **_bind(period)}).all()
    return [NamedCount(r.name, num(r.a), int(r.n)) for r in rows]


def suppliers(db: Session, sel: BranchSel, period: ReportPeriod) -> list[NamedCount]:
    return _grouped(db, sel, period, "supplier")


def subjects(db: Session, sel: BranchSel, period: ReportPeriod) -> list[NamedCount]:
    return _grouped(db, sel, period, "subject")


def by_branch(db: Session, sel: BranchSel, period: ReportPeriod) -> list[ProcBranch]:
    where, params = sel.rows("l.branch_id")
    lots_by = {int(r.branch_id): r for r in db.execute(text(
        f"SELECT l.branch_id, coalesce(sum(l.contract_price) FILTER (WHERE {_DONE} "
        "AND l.month_id = ANY(:ytd)), 0) AS ytd, "
        f"coalesce(sum(l.start_price - l.contract_price) FILTER (WHERE {_DONE} AND {_PERIOD}), 0) "
        f"AS savings FROM pub.agg_procurement_lots l WHERE {where} GROUP BY l.branch_id"),
        {**params, **_bind(period)}).all()}
    p_where, p_params = sel.rows("p.branch_id")
    plans = pairs(db.execute(text(
        f"SELECT p.branch_id, sum(p.plan) FROM pub.agg_procurement_plan p WHERE {p_where} "
        "AND p.month_id = :year01 GROUP BY p.branch_id"),
        {**p_params, "year01": period.last_month // 100 * 100 + 1}).all())
    ids = sorted(set(lots_by) | {int(b) for b in plans})
    if not ids:
        return []
    names = pairs(db.execute(text("SELECT branch_id, name FROM pub.branches "
                                 "WHERE branch_id = ANY(:ids)"), {"ids": ids}).all())
    out = [ProcBranch(i, names.get(i, str(i)), num(plans.get(i)),
                      num(lots_by[i].ytd) if i in lots_by else 0.0,
                      round(num(lots_by[i].savings), 2) if i in lots_by else 0.0) for i in ids]
    return sorted(out, key=lambda b: (-b.ytd, b.name))
