"""TZ 4 «Требует внимания» — ombor qoidalari (S3 spec 7).

Minimum (min_qty) yoki oxirgi harakat sanasi manbada bo'lmasa (1C'ning joriy javobi) qoida
o'tkazib yuboriladi — nol «past pozitsiya» yoki nol «неликвид» deb hisoblanmaydi.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.alerts.types import AlertHit, RuleConfig, breached, evaluator, hit
from app.sections.deps import SectionQuery
from app.sections.fmt import fmt_money, fmt_pct, plural
from app.sections.queries import stock


@evaluator("stock_below_minimum")
def stock_below_minimum(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    period, sel = q.period(), q.sel()
    totals = stock.totals(db, sel, period)
    if not totals.has_minimum or not breached(float(totals.below_min), rule):
        return None
    top = stock.positions(db, sel, period.last_month, "below", limit=2)
    word = plural(totals.below_min, "позиция", "позиции", "позиций")
    names = ", ".join(p.name for p in top)
    return hit(rule, f"{totals.below_min} {word} ниже минимального запаса: {names}",
               float(totals.below_min))


@evaluator("illiquid_stock_share")
def illiquid_stock_share(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    totals = stock.totals(db, q.sel(), q.period())
    share = totals.idle_share
    if share is None or not breached(share, rule):
        return None
    return hit(rule, f"{fmt_pct(share)} стоимости запасов без движения более 180 дней: "
                     f"{fmt_money(totals.idle_value)}", share)
