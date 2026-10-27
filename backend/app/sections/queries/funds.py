"""Целевое использование средств: использовано / выделено (TZ 4)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.sections.period import ReportPeriod
from app.sections.queries.cash import num
from app.sections.scope import BranchSel


@dataclass(frozen=True, slots=True)
class FundRow:
    key: int
    name: str
    allocated: float
    used: float

    @property
    def share(self) -> float | None:
        return round(self.used / self.allocated, 6) if self.allocated else None


def funds_by_source(db: Session, sel: BranchSel, period: ReportPeriod) -> list[FundRow]:
    where, params = sel.total()
    rows = db.execute(text(
        "SELECT source_id AS k, source_name AS n, sum(allocated) AS a, sum(used) AS u "
        f"FROM pub.agg_target_funds_month WHERE {where} AND month_id = ANY(:months) "
        "GROUP BY source_id, source_name ORDER BY a DESC, n"),
        {**params, "months": list(period.months)}).all()
    return [FundRow(int(r.k), r.n, num(r.a), num(r.u)) for r in rows]


def funds_by_branch(db: Session, sel: BranchSel, period: ReportPeriod) -> list[FundRow]:
    where, params = sel.rows("a.branch_id")
    rows = db.execute(text(
        "SELECT a.branch_id AS k, b.name AS n, sum(a.allocated) AS al, sum(a.used) AS u "
        "FROM pub.agg_target_funds_month a JOIN pub.branches b ON b.branch_id = a.branch_id "
        f"WHERE {where} AND a.month_id = ANY(:months) GROUP BY a.branch_id, b.name "
        "ORDER BY u DESC, n"), {**params, "months": list(period.months)}).all()
    return [FundRow(int(r.k), r.n, num(r.al), num(r.u)) for r in rows]
