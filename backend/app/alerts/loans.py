"""TZ 4 «Требует внимания» — kredit qoidalari (chegaralar core.alert_rules dan, S2 spec 7).

Kredit yoki kurs bo'lmasa qoida None qaytaradi (yolg'on signal yo'q): kursi yo'q kreditlar
portfel va ulushga kirmaydi.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.alerts.types import AlertHit, RuleConfig, breached, evaluator, hit
from app.sections.deps import SectionQuery
from app.sections.fmt import fmt_money, fmt_pct, plural
from app.sections.queries import loans


@evaluator("loan_payments_30d")
def loan_payments_30d(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    report = loans.load_report(db, q.sel(), q.period())
    due = [p for p in report.upcoming if breached((p.day - report.as_of).days, rule)]
    if not due:
        return None
    n = len(due)
    total = round(sum(t for t in (p.total for p in due) if t is not None), 2)
    first = due[0]
    word = plural(n, "платёж", "платежа", "платежей")
    return hit(rule, f"{n} {word} на {fmt_money(total)}, первый {first.day:%d.%m.%Y} — "
                     f"{first.creditor}", float(n))


@evaluator("fx_loans_share")
def fx_loans_share(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    report = loans.load_report(db, q.sel(), q.period())
    if report.fx_share is None or report.portfolio is None:
        return None
    if not breached(report.fx_share, rule):
        return None
    return hit(rule, f"{fmt_pct(report.fx_share)} портфеля в валюте: "
                     f"{fmt_money(report.fx_amount)} из {fmt_money(report.portfolio)}",
               report.fx_share)
