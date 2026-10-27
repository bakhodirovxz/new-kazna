"""Адресная инвестиционная программа (TZ 4 «Инвестиции (Адреса)») — faqat pub.agg_investment_month,
pub.agg_object_stages va pub.branches dan.

Davr yili = davr oxirgi oyining yili. План на отчётную дату = yil boshidan oldingi oylar rejasi +
oxirgi oy rejasi (ochiq oyda — o'tgan kunlar ulushi). Освоено ранее = yil boshigacha bo'lgan fakt
va ochilish qoldig'i. КС-2 va avans — davr oxirigacha oxirgi ma'lum qiymat (agregatda to'ldirilgan).
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dwh.dates import from_date_id, month_id
from app.sections.period import ReportPeriod
from app.sections.queries.cash import num, opt
from app.sections.queries.procurement import ratio
from app.sections.scope import BranchSel

ON_TRACK = 0.9  # TZ 4: «по графику ≥ 90%, отстаёт 75–90%, под угрозой < 75%»
THREAT = 0.75
GAP_PP = 20.0
ADVANCE_DAYS = 90


@dataclass(frozen=True, slots=True)
class InvObject:
    object_id: int
    object_code: str
    name: str
    program_code: str | None
    work_type: str
    source_name: str
    commissioning_year: int | None
    total_cost: float | None
    branch_id: int
    branch_name: str
    plan_year: float
    plan_to_date: float
    fact_ytd: float
    fact_period: float
    prior: float
    physical: float | None
    advance: float
    advance_days: int | None

    @property
    def execution(self) -> float | None:
        """Исполнение графика = факт / план на отчётную дату."""
        return ratio(self.fact_ytd, self.plan_to_date)

    @property
    def status(self) -> str | None:
        e = self.execution
        if e is None:
            return None
        return "ok" if e >= ON_TRACK else "lag" if e >= THREAT else "risk"

    @property
    def financial(self) -> float | None:
        """(освоено ранее + освоено в году) / общая стоимость объекта."""
        return ratio(self.prior + self.fact_ytd, self.total_cost or 0.0)

    @property
    def gap_pp(self) -> float | None:
        if self.financial is None or self.physical is None:
            return None
        return round((self.financial - self.physical) * 100, 1)


@dataclass(frozen=True, slots=True)
class InvTotals:
    objects: tuple[InvObject, ...]
    total_cost: float
    program: float
    plan_to_date: float
    fact_ytd: float
    fact_period: float
    lagging: int
    threatened: int
    commissioning: int
    year: int

    @property
    def execution(self) -> float | None:
        return ratio(self.fact_ytd, self.plan_to_date)

    @property
    def has_objects(self) -> bool:
        return bool(self.objects)


@dataclass(frozen=True, slots=True)
class CumPoint:
    month_id: int
    plan: float
    fact: float | None


@dataclass(frozen=True, slots=True)
class SourceRow:
    name: str
    plan_year: float
    fact_ytd: float

    @property
    def share(self) -> float | None:
        return ratio(self.fact_ytd, self.plan_year)


@dataclass(frozen=True, slots=True)
class StageRow:
    object_id: int
    stage_no: int
    name: str
    plan_date: date
    fact_date: date | None
    done: bool
    late: bool


def _fraction(period: ReportPeriod) -> float:
    if not period.open_last:
        return 1.0
    end = period.date_to
    return end.day / calendar.monthrange(end.year, end.month)[1]


def objects(db: Session, sel: BranchSel, period: ReportPeriod) -> list[InvObject]:
    last = period.last_month
    y01, y12 = last // 100 * 100 + 1, last // 100 * 100 + 12
    where, params = sel.rows("a.branch_id")
    rows = db.execute(text(
        "SELECT a.branch_id, b.name AS branch_name, a.object_id, a.object_code, a.name, "
        "a.program_code, a.work_type, a.source_name, a.commissioning_year, a.total_cost, "
        "coalesce(sum(a.plan) FILTER (WHERE a.month_id BETWEEN :y01 AND :y12), 0) AS plan_year, "
        "coalesce(sum(a.plan) FILTER (WHERE a.month_id >= :y01 AND a.month_id < :last), 0) "
        "AS plan_before, "
        "coalesce(sum(a.plan) FILTER (WHERE a.month_id = :last), 0) AS plan_last, "
        "coalesce(sum(a.fact) FILTER (WHERE a.month_id BETWEEN :y01 AND :last), 0) AS fact_ytd, "
        "coalesce(sum(a.fact) FILTER (WHERE a.month_id = ANY(:months)), 0) AS fact_period, "
        "coalesce(sum(a.fact) FILTER (WHERE a.month_id < :y01), 0) "
        "+ coalesce(sum(a.opening) FILTER (WHERE a.month_id <= :last), 0) AS prior, "
        "(array_agg(a.physical_pct ORDER BY a.month_id DESC) FILTER (WHERE a.month_id <= :last "
        "AND a.physical_pct IS NOT NULL))[1] AS phys, "
        "(array_agg(a.advance ORDER BY a.month_id DESC) FILTER (WHERE a.month_id <= :last "
        "AND a.advance IS NOT NULL))[1] AS adv, "
        "(array_agg(a.advance_date_id ORDER BY a.month_id DESC) FILTER (WHERE a.month_id <= :last "
        "AND a.advance IS NOT NULL))[1] AS adv_date "
        "FROM pub.agg_investment_month a JOIN pub.branches b ON b.branch_id = a.branch_id "
        f"WHERE {where} GROUP BY a.branch_id, b.name, a.object_id, a.object_code, a.name, "
        "a.program_code, a.work_type, a.source_name, a.commissioning_year, a.total_cost"),
        {**params, "y01": y01, "y12": y12, "last": last, "months": list(period.months)}).all()
    frac = _fraction(period)
    out: list[InvObject] = []
    for r in rows:
        plan_year, fact_ytd = num(r.plan_year), num(r.fact_ytd)
        if plan_year <= 0 and fact_ytd <= 0:
            continue
        advance = num(r.adv)
        days = None
        if advance > 0 and r.adv_date is not None:
            days = (period.date_to - from_date_id(int(r.adv_date))).days
        out.append(InvObject(
            object_id=int(r.object_id), object_code=r.object_code, name=r.name,
            program_code=r.program_code, work_type=r.work_type, source_name=r.source_name,
            commissioning_year=None if r.commissioning_year is None else int(r.commissioning_year),
            total_cost=opt(r.total_cost), branch_id=int(r.branch_id), branch_name=r.branch_name,
            plan_year=plan_year,
            plan_to_date=round(num(r.plan_before) + num(r.plan_last) * frac, 2),
            fact_ytd=fact_ytd, fact_period=num(r.fact_period), prior=num(r.prior),
            physical=opt(r.phys), advance=advance, advance_days=days))
    return sorted(out, key=lambda o: (-o.plan_year, o.name))


def totals(rows: list[InvObject], period: ReportPeriod) -> InvTotals:
    year = period.last_month // 100
    return InvTotals(
        objects=tuple(rows), total_cost=round(sum(o.total_cost or 0.0 for o in rows), 2),
        program=round(sum(o.plan_year for o in rows), 2),
        plan_to_date=round(sum(o.plan_to_date for o in rows), 2),
        fact_ytd=round(sum(o.fact_ytd for o in rows), 2),
        fact_period=round(sum(o.fact_period for o in rows), 2),
        lagging=sum(1 for o in rows if o.status in ("lag", "risk")),
        threatened=sum(1 for o in rows if o.status == "risk"),
        commissioning=sum(1 for o in rows if o.commissioning_year == year), year=year)


def cumulative(db: Session, sel: BranchSel, year: int, today: date) -> list[CumPoint]:
    months = [year * 100 + m for m in range(1, 13)]
    where, params = sel.rows("a.branch_id")
    by: dict[int, Any] = {int(r.month_id): r for r in db.execute(text(
        "SELECT a.month_id, sum(a.plan) AS plan, sum(a.fact) AS fact "
        f"FROM pub.agg_investment_month a WHERE {where} AND a.month_id = ANY(:m) "
        "GROUP BY a.month_id"), {**params, "m": months}).all()}
    current = month_id(today)
    out: list[CumPoint] = []
    plan = fact = 0.0
    for m in months:
        plan += num(by[m].plan) if m in by else 0.0
        fact += num(by[m].fact) if m in by else 0.0
        out.append(CumPoint(m, round(plan, 2), round(fact, 2) if m <= current else None))
    return out


def sources(rows: list[InvObject]) -> list[SourceRow]:
    plan: dict[str, float] = defaultdict(float)
    fact: dict[str, float] = defaultdict(float)
    for o in rows:
        plan[o.source_name] += o.plan_year
        fact[o.source_name] += o.fact_ytd
    out = [SourceRow(name, round(plan[name], 2), round(fact[name], 2)) for name in plan]
    return sorted(out, key=lambda s: (-s.plan_year, s.name))


def stages(db: Session, sel: BranchSel) -> dict[int, list[StageRow]]:
    where, params = sel.rows("s.branch_id")
    rows = db.execute(text(
        "SELECT s.object_id, s.stage_no, s.stage_name, s.plan_date_id, s.fact_date_id, s.done, "
        f"s.late FROM pub.agg_object_stages s WHERE {where} AND s.month_id = "
        f"(SELECT max(x.month_id) FROM pub.agg_object_stages x) "
        "ORDER BY s.object_id, s.stage_no"), params).all()
    out: dict[int, list[StageRow]] = defaultdict(list)
    for r in rows:
        out[int(r.object_id)].append(StageRow(
            object_id=int(r.object_id), stage_no=int(r.stage_no), name=r.stage_name,
            plan_date=from_date_id(int(r.plan_date_id)),
            fact_date=None if r.fact_date_id is None else from_date_id(int(r.fact_date_id)),
            done=bool(r.done), late=bool(r.late)))
    return dict(out)
