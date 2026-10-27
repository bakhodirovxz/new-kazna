"""Исполнение плана платежей, отклонение по статье, платёжные поручения, заявки в работе (TZ 4)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.sections.period import ReportPeriod
from app.sections.queries.cash import num
from app.sections.scope import BranchSel

PO_STATUSES = ("черновик", "на согласовании", "утверждено", "отправлено в банк", "исполнено",
               "отклонено")
IN_WORK = ("на согласовании", "утверждено")


@dataclass(frozen=True, slots=True)
class PlanFactRow:
    item_id: int
    name: str
    activity: str
    plan: float
    fact: float

    @property
    def execution(self) -> float | None:
        return round(self.fact / self.plan, 6) if self.plan else None

    @property
    def deviation(self) -> float:
        """TZ 4: план статьи − факт статьи."""
        return round(self.plan - self.fact, 2)


@dataclass(frozen=True, slots=True)
class StatusRow:
    status: str
    count: int
    amount: float


@dataclass(frozen=True, slots=True)
class RequestsRow:
    branch_id: int
    name: str
    count: int
    amount: float


def plan_fact(db: Session, sel: BranchSel, period: ReportPeriod) -> list[PlanFactRow]:
    where, params = sel.total("a.branch_id")
    rows = db.execute(text(
        "SELECT a.item_id, i.name, i.activity, sum(a.plan_amount) AS p, sum(a.fact_amount) AS f "
        "FROM pub.agg_payments_month a JOIN pub.items i ON i.item_id = a.item_id "
        f"WHERE {where} AND a.month_id = ANY(:months) "
        "GROUP BY a.item_id, i.name, i.activity "
        "HAVING sum(a.plan_amount) > 0 OR sum(a.fact_amount) > 0 ORDER BY p DESC, i.name"),
        {**params, "months": list(period.months)}).all()
    return [PlanFactRow(int(r.item_id), r.name, r.activity, num(r.p), num(r.f)) for r in rows]


def orders_by_status(db: Session, sel: BranchSel, period: ReportPeriod) -> list[StatusRow]:
    where, params = sel.total()
    got = {r.status: (int(r.n), num(r.s)) for r in db.execute(text(
        "SELECT status, sum(doc_count) AS n, sum(amount) AS s FROM pub.agg_payment_orders_month "
        f"WHERE {where} AND month_id = ANY(:months) GROUP BY status"),
        {**params, "months": list(period.months)}).all()}
    return [StatusRow(s, *got.get(s, (0, 0.0))) for s in PO_STATUSES]


def requests_total(db: Session, sel: BranchSel) -> tuple[int, float]:
    """Joriy holat: davrdan qat'i nazar «на согласовании» + «утверждено» (spec 4)."""
    where, params = sel.total()
    row = db.execute(text(
        "SELECT coalesce(sum(doc_count), 0) AS n, coalesce(sum(amount), 0) AS s "
        f"FROM pub.agg_payment_orders_month WHERE {where} AND status = ANY(:st)"),
        {**params, "st": list(IN_WORK)}).one()
    return int(row.n), num(row.s)


def requests_by_branch(db: Session, sel: BranchSel) -> list[RequestsRow]:
    where, params = sel.rows("a.branch_id")
    rows = db.execute(text(
        "SELECT a.branch_id, b.name, sum(a.doc_count) AS n, sum(a.amount) AS s "
        "FROM pub.agg_payment_orders_month a JOIN pub.branches b ON b.branch_id = a.branch_id "
        f"WHERE {where} AND a.status = ANY(:st) GROUP BY a.branch_id, b.name "
        "ORDER BY s DESC, b.name"), {**params, "st": list(IN_WORK)}).all()
    return [RequestsRow(int(r.branch_id), r.name, int(r.n), num(r.s)) for r in rows]
