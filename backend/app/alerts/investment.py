"""TZ 4 «Требует внимания» — АИП qoidalari (S4 spec 7).

investment_schedule — tanlov jamida; fin_phys_gap va advances_90d — obyekt bo'yicha (chegara
p.p. / kun), qiymat — chegaradan o'tgan obyektlar soni. Obyekt yo'q — None.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.alerts.types import AlertHit, RuleConfig, breached, evaluator, hit
from app.sections.deps import SectionQuery
from app.sections.fmt import fmt_money, fmt_num, fmt_pct, plural
from app.sections.queries import investment


@evaluator("investment_schedule")
def investment_schedule(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    period = q.period()
    t = investment.totals(investment.objects(db, q.sel(), period), period)
    execution = t.execution
    if execution is None or not breached(execution, rule):
        return None
    return hit(rule, f"Исполнение графика {fmt_pct(execution)}: освоено {fmt_money(t.fact_ytd)} "
                     f"из {fmt_money(t.plan_to_date)}", execution)


@evaluator("fin_phys_gap")
def fin_phys_gap(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    rows = [o for o in investment.objects(db, q.sel(), q.period())
            if o.gap_pp is not None and breached(o.gap_pp, rule)]
    if not rows:
        return None
    top = max(rows, key=lambda o: o.gap_pp or 0.0)
    n = len(rows)
    word = plural(n, "объект", "объекта", "объектов")
    return hit(rule, f"{n} {word}: финансирование опережает физическое выполнение, наибольший "
                     f"разрыв — {top.name} {fmt_num(top.gap_pp or 0.0, 0)} п.п.", float(n))


@evaluator("advances_90d")
def advances_90d(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    rows = [o for o in investment.objects(db, q.sel(), q.period())
            if o.advance > 0 and o.advance_days is not None
            and breached(float(o.advance_days), rule)]
    if not rows:
        return None
    n = len(rows)
    word = plural(n, "незакрытый аванс", "незакрытых аванса", "незакрытых авансов")
    total = sum(o.advance for o in rows)
    return hit(rule, f"{n} {word} старше {fmt_num(rule.value, 0)} дней на сумму "
                     f"{fmt_money(total)}", float(n))
