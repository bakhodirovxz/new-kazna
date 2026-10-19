"""fact_debt: shartnoma × sana (oy oxirlari va as_of) — debitor/kreditor, muddati o'tgan."""

from __future__ import annotations

from datetime import date

from app.dwh.dates import add_months, date_id, month_end, month_start
from app.etl.synthetic.model import ContractRef, SynthModel, money
from app.etl.synthetic.reference import BRANCH_BY_ID
from app.etl.types import StagingSink, Window


def _snapshot_days(model: SynthModel, contract: ContractRef) -> list[date]:
    days: list[date] = []
    cur = month_start(contract.contract_date)
    while cur <= model.as_of:
        day = model.period_end(cur)
        if day >= contract.contract_date:
            days.append(day)
        cur = add_months(cur, 1)
    last_active = month_end(contract.end_date)
    return [d for d in days if contract.late or d <= last_active]


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    count = 0
    for c in model.contracts:
        for day in _snapshot_days(model, c):
            if not window.contains(day):
                continue
            # Prototip debAt(): eski kesim kattaroq. Mos yozuv as_of'ga EMAS, shartnoma
            # tugash oyiga bog'langan — kesim (seed, oy) ning sof funksiyasi.
            months_left = max(0, (c.end_date.year - day.year) * 12 + c.end_date.month - day.month)
            outstanding = float(c.amount) * (1 + 0.025 * months_left)
            overdue_days = (day - c.due_date).days if c.late and day > c.due_date else 0
            overdue = outstanding * c.overdue_ratio if overdue_days else 0.0
            sink.add("fact_debt", {
                "doc_type": "debt_snapshot", "src_id": f"DEBT-{c.code}-{date_id(day)}",
                "date_id": date_id(day), "branch_code": BRANCH_BY_ID[c.branch_id].code,
                "contract_code": c.code, "cp_code": c.cp_code,
                "receivable": money(outstanding) if c.kind == "receivable" else 0,
                "payable": money(outstanding) if c.kind == "payable" else 0,
                "overdue": money(overdue), "overdue_days": overdue_days,
            })
            count += 1
    return {"fact_debt": count}
