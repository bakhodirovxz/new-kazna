"""TZ 4 «Требует внимания» — ishlab chiqarish qoidalari (chegaralar — core.alert_rules, S3 spec 7).

generation_plan — stansiya bo'yicha (seed: per=station): reja > 0 bo'lgan stansiyalardan bajarilishi
chegaradan past bo'lganlar soni. energy_payment_level — tanlov jamida оплачено / начислено.
Stansiya, reja yoki realizatsiya bo'lmasa — None (yolg'on signal yo'q).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.alerts.types import AlertHit, RuleConfig, breached, evaluator, hit
from app.sections.deps import SectionQuery
from app.sections.fmt import fmt_money, fmt_pct, plural
from app.sections.queries import production


@evaluator("generation_plan")
def generation_plan(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    sel = q.sel()
    if not production.has_stations(db, sel):
        return None
    low = sorted((s for s in production.stations(db, sel, q.period())
                  if s.execution is not None and breached(s.execution, rule)),
                 key=lambda s: (s.execution or 0.0, s.name))
    if not low:
        return None
    n = len(low)
    verb = plural(n, "ГЭС не выполняет", "ГЭС не выполняют", "ГЭС не выполняют")
    names = ", ".join(f"{s.short_name} {fmt_pct(s.execution or 0.0, 0)}" for s in low[:3])
    return hit(rule, f"{n} {verb} план выработки: {names}", float(n))


@evaluator("energy_payment_level")
def energy_payment_level(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    totals = production.totals(db, q.sel(), q.period())
    level = totals.payment_level
    if level is None or not breached(level, rule):
        return None
    return hit(rule, f"{fmt_pct(level)}: оплачено {fmt_money(totals.paid)} "
                     f"из {fmt_money(totals.accrued)}", level)
