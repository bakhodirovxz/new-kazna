"""Дебиторская/кредиторская/просроченная задолженность (TZ 4) — davr oxiridagi oy holati."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.sections.queries.cash import num
from app.sections.scope import BranchSel

_CONTRACT_COLS = (
    "c.contract_id, c.contract_number, c.cp_name, c.branch_id, b.name AS branch_name, c.kind, "
    "c.receivable + c.payable AS amount, c.overdue, c.overdue_days, c.end_date"
)


@dataclass(frozen=True, slots=True)
class DebtSummary:
    receivable: float
    payable: float
    overdue_receivable: float
    overdue_payable: float
    contracts: int


@dataclass(frozen=True, slots=True)
class ContractRow:
    contract_id: int
    number: str
    cp_name: str
    branch_id: int
    branch_name: str
    kind: str
    amount: float
    overdue: float
    overdue_days: int
    end_date: date | None


@dataclass(frozen=True, slots=True)
class DebtBranchRow:
    branch_id: int
    name: str
    receivable: float
    payable: float
    overdue_payable: float


def debt_summary(db: Session, sel: BranchSel, month: int) -> DebtSummary | None:
    where, params = sel.total()
    row = db.execute(text(
        "SELECT count(*) AS n, sum(receivable) AS r, sum(payable) AS p, "
        "sum(overdue_receivable) AS orr, sum(overdue_payable) AS op, sum(contracts) AS c "
        f"FROM pub.agg_debt_month WHERE {where} AND month_id = :m"), {**params, "m": month}).one()
    if not row.n:
        return None
    return DebtSummary(num(row.r), num(row.p), num(row.orr), num(row.op), int(row.c or 0))


def _contracts(db: Session, sql_tail: str, params: dict[str, object]) -> list[ContractRow]:
    rows = db.execute(text(
        f"SELECT {_CONTRACT_COLS} FROM pub.agg_debt_contracts c "
        f"JOIN pub.branches b ON b.branch_id = c.branch_id {sql_tail}"), params).all()
    return [ContractRow(int(r.contract_id), r.contract_number, r.cp_name, int(r.branch_id),
                        r.branch_name, r.kind, num(r.amount), num(r.overdue), int(r.overdue_days),
                        r.end_date) for r in rows]


def contracts(db: Session, sel: BranchSel, month: int, limit: int = 500) -> list[ContractRow]:
    """TZ 5: muddati o'tganlar birinchi (kunlar kamayishi bo'yicha), so'ng summa bo'yicha."""
    where, params = sel.rows("c.branch_id")
    return _contracts(db, f"WHERE {where} AND c.month_id = :m "
                          "ORDER BY (c.overdue_days > 0) DESC, c.overdue_days DESC, amount DESC, "
                          "c.contract_id LIMIT :lim", {**params, "m": month, "lim": limit})


def overdue_contracts(db: Session, sel: BranchSel, month: int,
                      min_days: float) -> list[ContractRow]:
    where, params = sel.rows("c.branch_id")
    return _contracts(db, f"WHERE {where} AND c.month_id = :m AND c.overdue_days > :d "
                          "ORDER BY c.overdue DESC, c.contract_id",
                      {**params, "m": month, "d": min_days})


def debt_by_branch(db: Session, sel: BranchSel, month: int) -> list[DebtBranchRow]:
    where, params = sel.rows("a.branch_id")
    rows = db.execute(text(
        "SELECT a.branch_id, b.name, a.receivable, a.payable, a.overdue_payable "
        "FROM pub.agg_debt_month a JOIN pub.branches b ON b.branch_id = a.branch_id "
        f"WHERE {where} AND a.month_id = :m ORDER BY a.payable DESC, b.name"),
        {**params, "m": month}).all()
    return [DebtBranchRow(int(r.branch_id), r.name, num(r.receivable), num(r.payable),
                          num(r.overdue_payable)) for r in rows]
