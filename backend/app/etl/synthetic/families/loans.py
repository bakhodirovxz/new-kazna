"""fact_loan_schedule: prototip LOANS grafigi (2026 … so'ndirish yili), summalar kredit valyutasida.

Prototipdagi summa (×1000) — mln so'm ekvivalenti; valyutaga REF_RATES bilan o'giriladi.
To'lov oylari prototip `pm` ro'yxatidan (0 — yanvar), sana — oyning 15-kuni.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.dwh.dates import date_id
from app.etl.synthetic.model import SynthModel, money
from app.etl.synthetic.reference import BRANCHES, LOANS
from app.etl.types import StagingSink, Window

REF_RATES = {"USD": 12500.0, "EUR": 13500.0, "CNY": 1736.0, "UZS": 1.0}
# Prototip `pm` (to'lov oylari) — LOANS tartibida.
PAY_MONTHS: tuple[tuple[int, ...], ...] = (
    (3, 9), (4, 10), (5, 11), (0, 6), (2, 8), (3, 9), tuple(range(12)), (2, 5, 8, 11),
)
FIRST_YEAR = 2026
LAST_YEAR = 2040  # shortcut: dwh.dim_date 2040-12-31 gacha (0005); 2041 so'ndirish kesiladi


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    count = 0
    for n, (loan, months) in enumerate(zip(LOANS, PAY_MONTHS, strict=True), start=1):
        _creditor, _project, b_index, currency, amount, rate, grace, end = loan
        balance = amount * 1000 / REF_RATES[currency]
        for year in range(FIRST_YEAR, min(end, LAST_YEAR) + 1):
            annual = balance / (end - year + 1) if year >= grace else 0.0
            for month in months:
                interest = balance * rate / len(months)
                principal = annual / len(months)
                balance -= principal
                day = date(year, month + 1, 15)
                if day < window.date_from:  # forward maqsad: faqat pastki chegara
                    continue
                sink.add("fact_loan_schedule", {
                    "doc_type": "loan_schedule", "src_id": f"LS-{n:02d}-{year}{month + 1:02d}",
                    "date_id": date_id(day), "branch_code": BRANCHES[b_index].code,
                    "loan_code": f"LOAN-{n:02d}", "principal": money(principal),
                    "interest": money(interest),
                    "balance": money(balance) if abs(balance) >= 0.005 else Decimal("0.00"),
                })
                count += 1
    return {"fact_loan_schedule": count}
