"""«Казначейство» (TZ 5): Сводка, Исполнение платежей, Платёжный календарь, Договоры и
задолженность, Целевые средства. Zanjir: router → queries (pub) → Cache.respond."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy.orm import Session

from app.auth.context import require_perm
from app.auth.permissions import Section, section_perm
from app.core.cache import Cache
from app.core.db import DB
from app.sections.deps import SQ, SectionQuery
from app.sections.obzor import build_item
from app.sections.queries import calendar, cash, debt, funds, payments
from app.sections.queries.calendar import CalendarBlock
from app.sections.queries.debt import ContractRow
from app.sections.queries.funds import FundRow
from app.sections.schemas import (
    BankBalanceOut,
    CalendarDayOut,
    CalendarOut,
    ContractRowOut,
    DebtBranchRowOut,
    FundRowOut,
    ItemBranchesOut,
    KaznaCalendarOut,
    KaznaCelevyeOut,
    KaznaDogovoryOut,
    KaznaKpisOut,
    KaznaPlatezhiOut,
    KaznaSvodOut,
    OrderStatusOut,
    PlanFactRowOut,
    RequestsRowOut,
    period_out,
)

router = APIRouter(prefix="/kazna", tags=["kazna"],
                   dependencies=[Depends(require_perm(section_perm(Section.KAZNA)))])


def build_kpis(db: Session, q: SectionQuery) -> KaznaKpisOut:
    period, sel = q.period(), q.sel()
    totals = cash.cash_totals(db, sel, period)
    plan_rows = payments.plan_fact(db, sel, period)
    plan = round(sum(r.plan for r in plan_rows), 2)
    fact = round(sum(r.fact for r in plan_rows), 2)
    orders = payments.orders_by_status(db, sel, period)
    req_count, req_amount = payments.requests_total(db, sel)
    summary = debt.debt_summary(db, sel, period.last_month)
    return KaznaKpisOut(
        balance=totals.closing, balance_date=period.date_to,
        banks=len(calendar.bank_balances(db, sel, period.last_month)),
        plan=plan, fact=fact, execution=round(fact / plan, 6) if plan else None,
        orders_count=sum(o.count for o in orders),
        orders_amount=round(sum(o.amount for o in orders), 2),
        requests_count=req_count, requests_amount=req_amount,
        receivable=summary.receivable if summary else None,
        payable=summary.payable if summary else None,
        overdue_payable=summary.overdue_payable if summary else None,
    )


def _plan_fact(db: Session, q: SectionQuery) -> list[PlanFactRowOut]:
    return [PlanFactRowOut(item_id=r.item_id, name=r.name, activity=r.activity, plan=r.plan,
                           fact=r.fact, execution=r.execution, deviation=r.deviation)
            for r in payments.plan_fact(db, q.sel(), q.period())]


def _orders(db: Session, q: SectionQuery) -> list[OrderStatusOut]:
    return [OrderStatusOut(status=o.status, count=o.count, amount=o.amount)
            for o in payments.orders_by_status(db, q.sel(), q.period())]


def calendar_out(block: CalendarBlock) -> CalendarOut:
    return CalendarOut(
        as_of=block.as_of, start=block.start,
        days=[CalendarDayOut(date=d.day, taxes=d.taxes, salary=d.salary, loans=d.loans,
                             contracts=d.contracts, total=d.total) for d in block.days],
        total=block.total, balance=block.balance, coverage=block.coverage)


def _banks(db: Session, q: SectionQuery) -> list[BankBalanceOut]:
    return [BankBalanceOut(bank_name=b.bank_name, balance=b.balance)
            for b in calendar.bank_balances(db, q.sel(), q.period().last_month)]


def _contract(c: ContractRow) -> ContractRowOut:
    return ContractRowOut(contract_id=c.contract_id, number=c.number, cp_name=c.cp_name,
                          branch_id=c.branch_id, branch_name=c.branch_name, kind=c.kind,
                          amount=c.amount, overdue=c.overdue, overdue_days=c.overdue_days,
                          end_date=c.end_date)


def _fund(f: FundRow) -> FundRowOut:
    return FundRowOut(key=f.key, name=f.name, allocated=f.allocated, used=f.used, share=f.share)


def build_svod(db: Session, q: SectionQuery) -> KaznaSvodOut:
    return KaznaSvodOut(
        period=period_out(q.period()), kpis=build_kpis(db, q), plan_fact=_plan_fact(db, q),
        orders=_orders(db, q), calendar=calendar_out(calendar.calendar(db, q.sel())),
        banks=_banks(db, q),
        contracts=[_contract(c) for c in debt.contracts(db, q.sel(), q.period().last_month, 50)])


def build_platezhi(db: Session, q: SectionQuery) -> KaznaPlatezhiOut:
    return KaznaPlatezhiOut(period=period_out(q.period()), kpis=build_kpis(db, q),
                            plan_fact=_plan_fact(db, q), orders=_orders(db, q))


def build_calendar(db: Session, q: SectionQuery) -> KaznaCalendarOut:
    return KaznaCalendarOut(
        period=period_out(q.period()), calendar=calendar_out(calendar.calendar(db, q.sel())),
        banks=_banks(db, q),
        requests=[RequestsRowOut(branch_id=r.branch_id, name=r.name, count=r.count,
                                 amount=r.amount)
                  for r in payments.requests_by_branch(db, q.sel())])


def build_dogovory(db: Session, q: SectionQuery) -> KaznaDogovoryOut:
    month = q.period().last_month
    return KaznaDogovoryOut(
        period=period_out(q.period()), kpis=build_kpis(db, q),
        contracts=[_contract(c) for c in debt.contracts(db, q.sel(), month, 500)],
        by_branch=[DebtBranchRowOut(branch_id=r.branch_id, name=r.name, receivable=r.receivable,
                                    payable=r.payable, overdue_payable=r.overdue_payable)
                   for r in debt.debt_by_branch(db, q.sel(), month)])


def build_celevye(db: Session, q: SectionQuery) -> KaznaCelevyeOut:
    period, sel = q.period(), q.sel()
    return KaznaCelevyeOut(period=period_out(period),
                           sources=[_fund(f) for f in funds.funds_by_source(db, sel, period)],
                           branches=[_fund(f) for f in funds.funds_by_branch(db, sel, period)])


@router.get("/svod", response_model=KaznaSvodOut)
def svod(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kazna.svod", q.cache_filters, lambda: build_svod(db, q))


@router.get("/platezhi", response_model=KaznaPlatezhiOut)
def platezhi(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kazna.platezhi", q.cache_filters, lambda: build_platezhi(db, q))


@router.get("/platezhi/items/{item_id}", response_model=ItemBranchesOut)
def platezhi_item(cache: Cache, db: DB, q: SQ, item_id: Annotated[int, Path(ge=1)]) -> Response:
    return cache.respond("kazna.item", {**q.cache_filters, "item": item_id},
                         lambda: build_item(db, q, item_id))


@router.get("/calendar", response_model=KaznaCalendarOut)
def calendar_page(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kazna.calendar", q.cache_filters, lambda: build_calendar(db, q))


@router.get("/dogovory", response_model=KaznaDogovoryOut)
def dogovory(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kazna.dogovory", q.cache_filters, lambda: build_dogovory(db, q))


@router.get("/celevye", response_model=KaznaCelevyeOut)
def celevye(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kazna.celevye", q.cache_filters, lambda: build_celevye(db, q))
