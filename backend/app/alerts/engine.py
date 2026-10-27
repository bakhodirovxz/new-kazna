"""Qoidalar har so'rovda filtrlar bilan tekshiriladi (TZ 4): chegaralar DB'dan, kritiklar birinchi.

Foydalanuvchi ko'ra olmaydigan bo'lim qoidalari hisoblanmaydi va ko'rsatilmaydi (qatorni bosish
o'sha bo'limga olib boradi). Evaluatori hali yo'q qoidalar (keyingi bo'limlar) o'tkazib yuboriladi.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

import app.alerts  # noqa: F401  (evaluatorlar ro'yxatga olinadi)
from app.alerts.types import REGISTRY, AlertHit, RuleConfig
from app.auth.permissions import Section, section_perm
from app.dwh.reference import ALERT_RULES
from app.sections.deps import SectionQuery
from app.sections.schemas import AlertCountOut, AlertOut, AlertsOut, period_out

_ORDER = {rule.code: i for i, rule in enumerate(ALERT_RULES)}


def load_rules(db: Session) -> list[RuleConfig]:
    rows = db.execute(text(
        "SELECT code, title, section, page, level, threshold FROM core.alert_rules "
        "WHERE is_current AND enabled")).all()
    rules = [RuleConfig(r.code, r.title, r.section, r.page, r.level, dict(r.threshold))
             for r in rows]
    return sorted(rules, key=lambda r: (_ORDER.get(r.code, len(_ORDER)), r.code))


def allowed_sections(permissions: frozenset[str]) -> list[str]:
    return sorted(s.value for s in Section if section_perm(s) in permissions)


def evaluate(db: Session, q: SectionQuery,
             permissions: frozenset[str]) -> tuple[list[AlertHit], list[str]]:
    sections = set(allowed_sections(permissions))
    hits: list[AlertHit] = []
    checked: list[str] = []
    for rule in load_rules(db):
        fn = REGISTRY.get(rule.code)
        if fn is None or rule.section not in sections:
            continue
        checked.append(rule.title)
        found = fn(db, q, rule)
        if found is not None:
            hits.append(found)
    hits.sort(key=lambda h: 0 if h.level == "critical" else 1)  # barqaror: ichida seed tartibi
    return hits, checked


def build_alerts(db: Session, q: SectionQuery, permissions: frozenset[str]) -> AlertsOut:
    hits, checked = evaluate(db, q, permissions)
    return AlertsOut(period=period_out(q.period()), checked=checked,
                     items=[AlertOut(code=h.code, level=h.level, title=h.title,
                                     message=h.message, section=h.section, page=h.page,
                                     value=h.value) for h in hits])


def build_count(db: Session, q: SectionQuery, permissions: frozenset[str]) -> AlertCountOut:
    hits, _ = evaluate(db, q, permissions)
    return AlertCountOut(count=len(hits), critical=sum(1 for h in hits if h.level == "critical"))
