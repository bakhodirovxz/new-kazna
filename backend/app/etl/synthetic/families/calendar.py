"""fact_payment_plan (doc_type=payment_schedule): as_of+1 … as_of+30 kunlar uchun sanali to'lovlar.

Prototip CAL_CATS g'oyasi: soliqlar 15 va 25-sanalarda, ish haqi 10 va 25-sanalarda, shartnomalar
bo'yicha to'lovlar ish kunlarida tasodifiy. Kredit to'lovlari bu yerda EMAS — loans oilasida
(fact_loan_schedule), kalendar agregati ularni ikki marta sanamaydi (spec 4).
"""

from __future__ import annotations

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
_BASE = {item.code: item for item in EXPENSE_ITEMS}


def _monthly(branch: BranchRef, code: str) -> float:
    item = _BASE[code]
    return item.base * share(branch, item.hq_share)


def _amounts(model: SynthModel, branch: BranchRef, day: date) -> list[tuple[str, float]]:
    r = rnd(model.seed, "sched", branch.id, date_id(day))
    out: list[tuple[str, float]] = []
    if day.day in (15, 25):
        out.append((TAX_ITEM, _monthly(branch, TAX_ITEM) / 2 * r.uniform(0.9, 1.1)))
    if day.day in (10, 25):
        out.append((SALARY_ITEM, _monthly(branch, SALARY_ITEM) / 2 * r.uniform(0.9, 1.1)))
    if r.random() < 0.5:
        code = r.choice(CONTRACT_ITEMS)
        out.append((code, _monthly(branch, code) / 21 * r.uniform(0.6, 1.5)))
    return [(code, amount) for code, amount in out if amount >= 0.01]


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    # Oyna faqat o'tgan davrni cheklaydi; jadval doim as_of dan keyingi 30 kun (forward maqsad).
    count = 0
    for branch in BRANCHES:
        for n in range(1, HORIZON_DAYS + 1):
            day = model.as_of + timedelta(days=n)
            if day.weekday() >= 5:
                continue
            for code, amount in _amounts(model, branch, day):
                sink.add("fact_payment_plan", {
                    "doc_type": SCHEDULE_DOC_TYPE,
                    "src_id": f"PS-{branch.id:02d}-{code}-{date_id(day)}",
                    "date_id": date_id(day), "branch_code": branch.code, "item_code": code,
                    "amount": money(amount),
                })
                count += 1
    return {"fact_payment_plan": count}
