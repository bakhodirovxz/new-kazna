"""TZ 4 «Требует внимания» — xarid qoidalari (chegaralar — core.alert_rules, S4 spec 7).

Lotlar/shartnomalar/reja bo'lmasa qoida o'tkazib yuboriladi (yolg'on signal yo'q).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.alerts.types import AlertHit, RuleConfig, breached, evaluator, hit
from app.sections.deps import SectionQuery
from app.sections.fmt import fmt_money, fmt_pct, plural
from app.sections.queries import procurement


@evaluator("procurement_overdue_lots")
def procurement_overdue_lots(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    t = procurement.totals(db, q.sel(), q.period())
    if t.in_work == 0 or not breached(float(t.overdue), rule):
        return None
    word = plural(t.overdue, "лот закупки просрочен", "лота закупки просрочены",
                  "лотов закупки просрочены")
    return hit(rule, f"{t.overdue} {word}: начальная цена {fmt_money(t.overdue_start)}, "
                     "дольше норматива на 10+ дней", float(t.overdue))


@evaluator("direct_contracts_share")
def direct_contracts_share(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    t = procurement.totals(db, q.sel(), q.period())
    share = t.direct_share
    if share is None or not breached(share, rule):
        return None
    return hit(rule, f"{fmt_pct(share)} суммы договоров заключено без конкурса: "
                     f"{fmt_money(t.direct)}", share)


@evaluator("procurement_plan")
def procurement_plan(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    t = procurement.totals(db, q.sel(), q.period())
    execution = t.plan_execution
    if execution is None or not breached(execution, rule):
        return None
    return hit(rule, f"Исполнено {fmt_pct(execution)}: {fmt_money(t.ytd)} из "
                     f"{fmt_money(t.plan)} с начала года", execution)
