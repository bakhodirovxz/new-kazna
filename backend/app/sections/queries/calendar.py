"""Платёжный календарь (14 kun × 4 tur), покрытие платежей остатком, остатки по банкам (TZ 4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dwh.dates import from_date_id, month_id
from app.sections.queries.cash import num, opt
from app.sections.scope import BranchSel


@dataclass(frozen=True, slots=True)
class CalendarDayRow:
    day: date
    taxes: float = 0.0
    salary: float = 0.0
    loans: float = 0.0
    contracts: float = 0.0

    @property
    def total(self) -> float:
        return round(self.taxes + self.salary + self.loans + self.contracts, 2)


@dataclass(frozen=True, slots=True)
class CalendarBlock:
    as_of: date | None
    days: list[CalendarDayRow] = field(default_factory=list)
    total: float = 0.0
    balance: float | None = None

    @property
    def start(self) -> date | None:
        return None if self.as_of is None else self.as_of + timedelta(days=1)

    @property
    def coverage(self) -> float | None:
        """Остаток на счетах / сумма платежей календаря."""
        if self.balance is None or not self.total:
            return None
        return self.balance / self.total


@dataclass(frozen=True, slots=True)
class BankBalance:
    bank_name: str
    balance: float


def current_balance(db: Session, sel: BranchSel, month: int) -> float | None:
    where, params = sel.total()
    return opt(db.execute(text(
        f"SELECT sum(closing_balance) FROM pub.agg_cash_month WHERE item_id = 0 AND {where} "
        "AND month_id = :m"), {**params, "m": month}).scalar_one())


def calendar(db: Session, sel: BranchSel) -> CalendarBlock:
    where, params = sel.total()
    as_of_id = db.execute(text(f"SELECT max(as_of_id) FROM pub.agg_calendar_day WHERE {where}"),
                          params).scalar_one()
    if as_of_id is None:
        return CalendarBlock(None)
    as_of = from_date_id(int(as_of_id))
    amounts: dict[int, dict[str, float]] = {}
    for r in db.execute(text(
            "SELECT date_id, kind, sum(amount) AS v FROM pub.agg_calendar_day "
            f"WHERE {where} GROUP BY date_id, kind"), params).all():
        amounts.setdefault(int(r.date_id), {})[r.kind] = num(r.v)
    days = [CalendarDayRow(from_date_id(d), **amounts[d]) for d in sorted(amounts)]
    total = round(sum(d.total for d in days), 2)
    return CalendarBlock(as_of, days, total, current_balance(db, sel, month_id(as_of)))


def bank_balances(db: Session, sel: BranchSel, month: int) -> list[BankBalance]:
    where, params = sel.total()
    rows = db.execute(text(
        "SELECT bank_name, sum(closing_balance) AS v FROM pub.agg_cash_bank_month "
        f"WHERE {where} AND month_id = :m AND closing_balance IS NOT NULL "
        "GROUP BY bank_name ORDER BY v DESC, bank_name"), {**params, "m": month}).all()
    return [BankBalance(r.bank_name, num(r.v)) for r in rows]
