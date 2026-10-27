"""TZ 4 «Требует внимания» — g'aznachilik qoidalari (chegaralar core.alert_rules dan).

Ma'lumot bo'lmasa (qoldiqlar, reja, qarzdorlik) qoida None qaytaradi — yolg'on signal yo'q.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.alerts.types import AlertHit, RuleConfig, breached, evaluator, hit
from app.sections.deps import SectionQuery
from app.sections.fmt import fmt_money, fmt_pct, plural
from app.sections.queries import calendar, cash, debt, payments


@evaluator("cash_below_monthly_outflow")
def cash_below_monthly_outflow(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    period = q.period()
    totals = cash.cash_totals(db, q.sel(), period)
    months = period.month_equivalents
    if totals.closing is None or totals.outflow <= 0 or months <= 0:
        return None
    average = totals.outflow / months
    ratio = totals.closing / average
    if not breached(ratio, rule):
        return None
    return hit(rule, f"{fmt_money(totals.closing)} при среднем расходовании "
                     f"{fmt_money(average)} в месяц", ratio)


@evaluator("payments_14d_exceed_balance")
def payments_14d_exceed_balance(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    block = calendar.calendar(db, q.sel())
    if block.balance is None or block.total <= 0:
        return None
    ratio = block.total / block.balance if block.balance > 0 else float("inf")
    if not breached(ratio, rule):
        return None
    return hit(rule, f"к оплате {fmt_money(block.total)} за 14 дней, на счетах "
                     f"{fmt_money(block.balance)}", ratio)


@evaluator("payment_plan_execution")
def payment_plan_execution(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    rows = payments.plan_fact(db, q.sel(), q.period())
    plan = sum(r.plan for r in rows)
    if plan <= 0:
        return None
    fact = sum(r.fact for r in rows)
    ratio = fact / plan
    if not breached(ratio, rule):
        return None
    return hit(rule, f"исполнение {fmt_pct(ratio)}, отклонение {fmt_money(plan - fact)}", ratio)


@evaluator("contracts_overdue_90d")
def contracts_overdue_90d(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    rows = [c for c in debt.overdue_contracts(db, q.sel(), q.period().last_month, 0)
            if breached(c.overdue_days, rule)]
    if not rows:
        return None
    total = sum(c.overdue for c in rows)
    biggest = max(rows, key=lambda c: c.overdue)
    n = len(rows)
    word = plural(n, "договор", "договора", "договоров")
    verb = "просрочен" if word == "договор" else "просрочены"
    return hit(rule, f"{n} {word} {verb} более {int(rule.value)} дней на сумму "
                     f"{fmt_money(total)}, крупнейший: {biggest.cp_name}", float(n))


@evaluator("overdue_payables_share")
def overdue_payables_share(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    summary = debt.debt_summary(db, q.sel(), q.period().last_month)
    if summary is None or summary.payable <= 0:
        return None
    share = summary.overdue_payable / summary.payable
    if not breached(share, rule):
        return None
    return hit(rule, f"{fmt_money(summary.overdue_payable)} из {fmt_money(summary.payable)} "
                     f"кредиторской задолженности ({fmt_pct(share)})", share)
