"""Kadrlar (TZ 4 «Кадры») — faqat pub.agg_hr_month, pub.agg_cash_month/pub.items va pub.branches.

Штат/факт — davr oxirgi oyidan kechmagan eng oxirgi ma'lumotli oy (oylik fayl hali kelmagan joriy
oyda nol ko'rsatilmasin). ФОТ — pul oqimidan: `kazna.calendar_kinds.salary` statyalari rasxodi
(TZ formulasi); доля — ФОТ / tanlovning barcha rasxodi. O'rtacha ish haqi = ФОТ / численность /
oylar (ochiq oy — o'tgan kunlar ulushi). Qo'nimsizlik = уволено / численность (yilga
hisoblanmaydi). Faqat agregatlar — ФИО yo'q (TZ 9).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dwh.dates import month_id
from app.sections.period import ReportPeriod
from app.sections.queries.cash import num
from app.sections.queries.procurement import pairs, ratio
from app.sections.scope import BranchSel

_NO_CODE = ["—"]  # bo'sh ro'yxat o'rniga (ANY('{}') turini PG aniqlay olmaydi)


def _codes(salary_codes: list[str]) -> list[str]:
    return list(salary_codes) or _NO_CODE


class _Derived:
    """Filial va jami uchun umumiy hosila xossalar (maydonlar — voris dataclass'larda)."""

    __slots__ = ()
    plan: float
    fact: float
    payroll: float
    fired: int
    overtime: float
    months: float

    @property
    def vacancies(self) -> float | None:
        return None if self.plan <= 0 else round(self.plan - self.fact, 1)

    @property
    def vacancy_share(self) -> float | None:
        return None if self.vacancies is None else ratio(self.vacancies, self.plan)

    @property
    def fill(self) -> float | None:
        return ratio(self.fact, self.plan)

    @property
    def avg_salary(self) -> float | None:
        """Средняя зарплата = ФОТ / численность / число месяцев периода."""
        if self.fact <= 0 or self.months <= 0:
            return None
        return round(self.payroll / self.fact / self.months, 6)

    @property
    def turnover(self) -> float | None:
        return ratio(float(self.fired), self.fact)

    @property
    def overtime_per_employee(self) -> float | None:
        return ratio(self.overtime, self.fact)


@dataclass(frozen=True, slots=True)
class HrFigures(_Derived):
    snap_month: int | None
    plan: float
    fact: float
    payroll: float
    outflow: float
    hired: int
    fired: int
    overtime: float
    months: float

    @property
    def payroll_share(self) -> float | None:
        return ratio(self.payroll, self.outflow)

    @property
    def has_data(self) -> bool:
        return self.fact > 0 or self.plan > 0


@dataclass(frozen=True, slots=True)
class HrBranch(_Derived):
    branch_id: int
    name: str
    plan: float
    fact: float
    payroll: float
    hired: int
    fired: int
    overtime: float
    months: float


@dataclass(frozen=True, slots=True)
class HrMonth:
    month_id: int
    payroll: float
    fact: float
    avg_salary: float | None
    hired: int
    fired: int
    overtime: float


@dataclass(frozen=True, slots=True)
class NamedValue:
    name: str
    value: float


def _snap_month(db: Session, where: str, params: dict[str, Any], last: int) -> int | None:
    value = db.execute(text(
        f"SELECT max(h.month_id) FROM pub.agg_hr_month h WHERE {where} AND h.month_id <= :last "
        "AND (h.headcount_fact > 0 OR h.headcount_plan > 0)"), {**params, "last": last}).scalar()
    return None if value is None else int(value)


def _payroll(db: Session, where: str, params: dict[str, Any], months: list[int],
             codes: list[str]) -> tuple[float, float]:
    row = db.execute(text(
        "SELECT coalesce(sum(c.outflow) FILTER (WHERE i.code = ANY(:codes)), 0) AS pay, "
        "coalesce(sum(c.outflow), 0) AS total FROM pub.agg_cash_month c "
        f"JOIN pub.items i ON i.item_id = c.item_id WHERE {where} AND c.month_id = ANY(:months)"),
        {**params, "codes": _codes(codes), "months": months}).one()
    return num(row.pay), num(row.total)


def totals(db: Session, sel: BranchSel, period: ReportPeriod,
           salary_codes: list[str]) -> HrFigures:
    where, params = sel.total("h.branch_id")
    snap = _snap_month(db, where, params, period.last_month)
    head = db.execute(text(
        "SELECT coalesce(sum(h.headcount_plan), 0) AS plan, "
        "coalesce(sum(h.headcount_fact), 0) AS fact FROM pub.agg_hr_month h "
        f"WHERE {where} AND h.month_id = :snap"), {**params, "snap": snap or 0}).one()
    flow = db.execute(text(
        "SELECT coalesce(sum(h.hired), 0) AS hired, coalesce(sum(h.fired), 0) AS fired, "
        "coalesce(sum(h.overtime_hours), 0) AS ot FROM pub.agg_hr_month h "
        f"WHERE {where} AND h.month_id = ANY(:months)"),
        {**params, "months": list(period.months)}).one()
    c_where, c_params = sel.total("c.branch_id")
    payroll, outflow = _payroll(db, c_where, c_params, list(period.months), salary_codes)
    return HrFigures(
        snap_month=snap, plan=num(head.plan), fact=num(head.fact), payroll=payroll,
        outflow=outflow, hired=int(flow.hired), fired=int(flow.fired), overtime=num(flow.ot),
        months=round(period.month_equivalents, 6))


def categories(db: Session, sel: BranchSel, period: ReportPeriod) -> list[NamedValue]:
    where, params = sel.total("h.branch_id")
    snap = _snap_month(db, where, params, period.last_month)
    rows = db.execute(text(
        "SELECT h.category, sum(h.headcount_fact) AS v FROM pub.agg_hr_month h "
        f"WHERE {where} AND h.month_id = :snap GROUP BY h.category "
        "HAVING sum(h.headcount_fact) > 0 ORDER BY v DESC, h.category"),
        {**params, "snap": snap or 0}).all()
    return [NamedValue(r.category, num(r.v)) for r in rows]


def by_branch(db: Session, sel: BranchSel, period: ReportPeriod,
              salary_codes: list[str]) -> list[HrBranch]:
    where, params = sel.rows("h.branch_id")
    x_where, _ = sel.rows("x.branch_id")
    head = {int(r.branch_id): r for r in db.execute(text(
        "SELECT h.branch_id, sum(h.headcount_plan) AS plan, sum(h.headcount_fact) AS fact "
        "FROM pub.agg_hr_month h JOIN (SELECT x.branch_id, max(x.month_id) AS m "
        f"FROM pub.agg_hr_month x WHERE {x_where} AND x.month_id <= :last "
        "GROUP BY x.branch_id) s ON s.branch_id = h.branch_id AND s.m = h.month_id "
        "GROUP BY h.branch_id"), {**params, "last": period.last_month}).all()}
    flow = {int(r.branch_id): r for r in db.execute(text(
        "SELECT h.branch_id, sum(h.hired) AS hired, sum(h.fired) AS fired, "
        "sum(h.overtime_hours) AS ot FROM pub.agg_hr_month h "
        f"WHERE {where} AND h.month_id = ANY(:months) GROUP BY h.branch_id"),
        {**params, "months": list(period.months)}).all()}
    c_where, c_params = sel.rows("c.branch_id")
    pay = pairs(db.execute(text(
        "SELECT c.branch_id, sum(c.outflow) FROM pub.agg_cash_month c "
        f"JOIN pub.items i ON i.item_id = c.item_id WHERE {c_where} "
        "AND c.month_id = ANY(:months) AND i.code = ANY(:codes) GROUP BY c.branch_id"),
        {**c_params, "months": list(period.months), "codes": _codes(salary_codes)}).all())
    ids = sorted(set(head) | set(flow))
    if not ids:
        return []
    names = pairs(db.execute(text("SELECT branch_id, name FROM pub.branches "
                                 "WHERE branch_id = ANY(:ids)"), {"ids": ids}).all())
    months = round(period.month_equivalents, 6)
    out = [HrBranch(
        branch_id=i, name=names.get(i, str(i)),
        plan=num(head[i].plan) if i in head else 0.0, fact=num(head[i].fact) if i in head else 0.0,
        payroll=num(pay.get(i)), hired=int(flow[i].hired) if i in flow else 0,
        fired=int(flow[i].fired) if i in flow else 0,
        overtime=num(flow[i].ot) if i in flow else 0.0, months=months) for i in ids]
    return sorted(out, key=lambda b: (-b.fact, b.name))


def monthly(db: Session, sel: BranchSel, today: date,
            salary_codes: list[str]) -> list[HrMonth]:
    months = [today.year * 100 + m for m in range(1, month_id(today) % 100 + 1)]
    where, params = sel.total("h.branch_id")
    by = {int(r.month_id): r for r in db.execute(text(
        "SELECT h.month_id, sum(h.headcount_fact) AS fact, sum(h.hired) AS hired, "
        "sum(h.fired) AS fired, sum(h.overtime_hours) AS ot FROM pub.agg_hr_month h "
        f"WHERE {where} AND h.month_id = ANY(:m) GROUP BY h.month_id"),
        {**params, "m": months}).all()}
    c_where, c_params = sel.total("c.branch_id")
    pay = pairs(db.execute(text(
        "SELECT c.month_id, sum(c.outflow) FROM pub.agg_cash_month c "
        f"JOIN pub.items i ON i.item_id = c.item_id WHERE {c_where} "
        "AND c.month_id = ANY(:m) AND i.code = ANY(:codes) GROUP BY c.month_id"),
        {**c_params, "m": months, "codes": _codes(salary_codes)}).all())
    current = month_id(today)
    part = today.day / calendar.monthrange(today.year, today.month)[1]
    out: list[HrMonth] = []
    for m in months:
        row = by.get(m)
        fact = num(row.fact) if row else 0.0
        payroll = num(pay.get(m))
        share = part if m == current else 1.0
        avg = None if fact <= 0 else round(payroll / fact / share, 6)
        out.append(HrMonth(m, payroll, fact, avg, int(row.hired) if row else 0,
                           int(row.fired) if row else 0, num(row.ot) if row else 0.0))
    return out
