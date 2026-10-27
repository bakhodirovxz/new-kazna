"""TZ 4 «Требует внимания» — kadrlar qoidalari (S4 spec 7). Faqat agregatlar.

Штат yoki численность ma'lumoti yo'q — None. ФОТ kerak emas (statya ro'yxati bo'sh beriladi).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.alerts.types import AlertHit, RuleConfig, breached, evaluator, hit
from app.sections.deps import SectionQuery
from app.sections.fmt import fmt_num, fmt_pct, plural
from app.sections.queries import hr


def _totals(db: Session, q: SectionQuery) -> hr.HrFigures:
    return hr.totals(db, q.sel(), q.period(), [])


@evaluator("vacancies_share")
def vacancies_share(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    t = _totals(db, q)
    share, vacancies = t.vacancy_share, t.vacancies
    if share is None or vacancies is None or not breached(share, rule):
        return None
    n = round(vacancies)
    word = plural(n, "вакансия", "вакансии", "вакансий")
    return hit(rule, f"{fmt_pct(share)} штата не занято: {fmt_num(vacancies, 0)} {word} из "
                     f"{fmt_num(t.plan, 0)}", share)


@evaluator("turnover")
def turnover(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    t = _totals(db, q)
    value = t.turnover
    if value is None or not breached(value, rule):
        return None
    return hit(rule, f"Текучесть {fmt_pct(value)}: уволено {t.fired} из {fmt_num(t.fact, 0)} "
                     "работников за период", value)


@evaluator("overtime")
def overtime(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    t = _totals(db, q)
    value = t.overtime_per_employee
    if value is None or not breached(value, rule):
        return None
    return hit(rule, f"{fmt_num(value)} ч сверхурочных на работника: всего "
                     f"{fmt_num(t.overtime, 0)} ч за период", value)
