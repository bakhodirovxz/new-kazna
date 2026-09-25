"""fact_cashflow (bank проводкалари) va fact_balance (hisob × sana qoldig'i)."""

from __future__ import annotations

from datetime import timedelta

from app.dwh.dates import date_id
from app.etl.synthetic.model import SynthModel
from app.etl.synthetic.reference import BRANCH_BY_ID
from app.etl.types import StagingSink, Window


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    cash = model.cash
    counts = {"fact_cashflow": 0, "fact_balance": 0}
    for p in cash.postings:
        if not window.contains(p.day):
            continue
        branch = BRANCH_BY_ID[p.branch_id].code
        sink.add("fact_cashflow", {
            "doc_type": "bank_entry", "src_id": p.src_id, "date_id": date_id(p.day),
            "branch_code": branch, "item_code": p.item_code, "direction": p.direction,
            "amount": p.amount, "gl_account": p.gl_account, "cp_code": p.cp_code,
            "contract_code": p.contract_code, "bank_code": f"ACC-{p.branch_id:02d}-{p.bank + 1}",
        })
        counts["fact_cashflow"] += 1
    # Oyna boshidagi ochilish qoldig'i ham kerak — bir kun oldingi qatorlar ham beriladi.
    first = window.date_from - timedelta(days=1)
    for row in cash.balances:
        if not first <= row.day <= window.date_to:
            continue
        bank = f"ACC-{row.branch_id:02d}-{row.bank + 1}"
        sink.add("fact_balance", {
            "doc_type": "statement", "src_id": f"BAL-{bank}-{date_id(row.day)}",
            "date_id": date_id(row.day), "branch_code": BRANCH_BY_ID[row.branch_id].code,
            "bank_code": bank, "balance": row.balance,
        })
        counts["fact_balance"] += 1
    return counts
