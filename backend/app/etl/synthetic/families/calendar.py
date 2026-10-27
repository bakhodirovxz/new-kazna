"""fact_payment_plan (doc_type=payment_schedule): as_of+1 … as_of+30 kunlar uchun sanali to'lovlar.

Prototip CAL_CATS g'oyasi. Ruling A-S1.R1: istalgan 14 kunlik oynada hamma tur ko'rinishi uchun
soliqlar oyda 4 marta (5, 15, 25-sana va oy oxiri), ish haqi 4 marta (4, 10, 18, 25-sana),
shartnomalar bo'yicha to'lovlar har ish kuni; dam olish kuniga tushgan sana OLDINGI ish kuniga
suriladi (tushib qolmaydi). Kredit to'lovlari bu yerda EMAS — loans oilasida (fact_loan_schedule),
kalendar agregati ularni ikki marta sanamaydi (spec 4).
"""

from __future__ import annotations

import calendar as _cal
from datetime import date, timedelta

from app.dwh.dates import date_id
from app.dwh.targets import SCHEDULE_DOC_TYPE
from app.etl.synthetic.model import SynthModel, money
from app.etl.synthetic.reference import BRANCHES, EXPENSE_ITEMS, BranchRef, share
from app.etl.synthetic.rng import rnd
from app.etl.types import StagingSink, Window

HORIZON_DAYS = 30
TAX_ITEM = "PKM54-O03"
SALARY_ITEM = "PKM54-O05"
CONTRACT_ITEMS = ("PKM54-O01", "PKM54-O02", "PKM54-O06", "PKM54-O07")
TAX_DAYS = (5, 15, 25, 0)  # 0 — oy oxiri
SALARY_DAYS = (4, 10, 18, 25)
_BASE = {item.code: item for item in EXPENSE_ITEMS}


def prev_workday(day: date) -> date:
    """Shanba/yakshanba — oldingi juma."""
    return day - timedelta(days=max(0, day.weekday() - 4))


def _monthly(branch: BranchRef, code: str) -> float:
    item = _BASE[code]
    return item.base * share(branch, item.hq_share)


def _amounts(model: SynthModel, branch: BranchRef, day: date) -> list[tuple[str, float]]:
    """`day` — NOMINAL sana (dam olish kuni bo'lishi mumkin); tasodif nominal sanaga bog'langan."""
    r = rnd(model.seed, "sched", branch.id, date_id(day))
    out: list[tuple[str, float]] = []
    last = _cal.monthrange(day.year, day.month)[1]
    if day.day in [last if d == 0 else d for d in TAX_DAYS]:
        out.append((TAX_ITEM, _monthly(branch, TAX_ITEM) / len(TAX_DAYS) * r.uniform(0.9, 1.1)))
    if day.day in SALARY_DAYS:
        out.append((SALARY_ITEM,
                    _monthly(branch, SALARY_ITEM) / len(SALARY_DAYS) * r.uniform(0.9, 1.1)))
    for code in CONTRACT_ITEMS:
        if day.weekday() < 5 and r.random() < 0.6:
            out.append((code, _monthly(branch, code) / 21 * r.uniform(0.6, 1.5)))
    return [(code, amount) for code, amount in out if amount >= 0.01]


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    # Oyna faqat o'tgan davrni cheklaydi; jadval doim as_of dan keyingi 30 kun (forward maqsad).
    count = 0
    for branch in BRANCHES:
        # +2: dam olish kunidagi nominal sana oldingi ish kuniga siljiydi.
        for n in range(1, HORIZON_DAYS + 3):
            nominal = model.as_of + timedelta(days=n)
            day = prev_workday(nominal)
            if not model.as_of < day <= model.as_of + timedelta(days=HORIZON_DAYS):
                continue
            for code, amount in _amounts(model, branch, nominal):
                sink.add("fact_payment_plan", {
                    "doc_type": SCHEDULE_DOC_TYPE,
                    "src_id": f"PS-{branch.id:02d}-{code}-{date_id(day)}",
                    "date_id": date_id(day), "branch_code": branch.code, "item_code": code,
                    "amount": money(amount),
                })
                count += 1
    return {"fact_payment_plan": count}
