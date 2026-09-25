"""fact_payment_plan (statya × oy × filial) va fact_payment_order (to'lov topshiriqlari)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from app.dwh.dates import date_id, month_id
from app.etl.synthetic.model import SynthModel, money, workdays
from app.etl.synthetic.reference import (
    BANKS,
    BRANCHES,
    EXPENSE_ITEMS,
    HQ_ID,
    PO_STATUSES,
    SUPPLIER_CODES,
    BranchRef,
    share,
)
from app.etl.synthetic.rng import rnd
from app.etl.types import StagingSink, Window

_STATUS_NAMES = [s for s, _ in PO_STATUSES]
_STATUS_WEIGHTS = [w for _, w in PO_STATUSES]


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    counts = {"fact_payment_plan": 0, "fact_payment_order": 0}
    current = month_id(model.as_of)
    outflow: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
    for p in model.cash.postings:
        if p.direction == "out":
            outflow[(p.branch_id, month_id(p.day))] += p.amount
    for branch in BRANCHES:
        for month in model.months():
            ym = month_id(month)
            if window.contains(month):
                for item in EXPENSE_ITEMS:
                    full = model.cash.full_amounts.get((branch.id, ym, item.code))
                    if full is None:
                        continue
                    r = rnd(model.seed, "plan", branch.id, item.code, ym)
                    if ym == current:
                        plan = full * r.uniform(0.95, 1.08)
                    else:
                        plan = full / r.uniform(0.82, 1.02)
                    sink.add("fact_payment_plan", {
                        "doc_type": "payment_plan",
                        "src_id": f"PP-{branch.id:02d}-{item.code}-{ym}",
                        "date_id": date_id(month), "branch_code": branch.code,
                        "item_code": item.code, "amount": money(plan),
                    })
                    counts["fact_payment_plan"] += 1
            counts["fact_payment_order"] += _orders(model, branch, month,
                                                    outflow[(branch.id, ym)], window, sink)
    return counts


def _orders(model: SynthModel, branch: BranchRef, month: date, total: Decimal, window: Window,
            sink: StagingSink) -> int:
    ym = month_id(month)
    r = rnd(model.seed, "po", branch.id, ym)
    count = round((55 if branch.id == HQ_ID else branch.weight * 42) * r.uniform(0.85, 1.15))
    current = ym == month_id(model.as_of)
    if current:
        count = max(1, round(count * 0.55))
    reject = r.uniform(0.02, 0.06)
    days = [d for d in workdays(month) if d <= model.as_of]
    if count == 0 or total <= 0 or not days:
        return 0
    item_weights = [e.base * share(branch, e.hq_share) for e in EXPENSE_ITEMS]
    shares = model.bank_shares[branch.id]
    added = 0
    for n in range(1, count + 1):
        day = r.choice(days)
        amount = money(float(total) / count * r.uniform(0.7, 1.3))
        item = r.choices(EXPENSE_ITEMS, weights=item_weights)[0]
        cp = r.choice(SUPPLIER_CODES)
        bank = r.choices(range(len(BANKS)), weights=shares)[0]
        if current:
            status = r.choices(_STATUS_NAMES, weights=_STATUS_WEIGHTS)[0]
        else:
            status = "отклонено" if r.random() < reject else "исполнено"
        status_day = min(day + timedelta(days=r.randint(0, 3)), model.as_of)
        if not window.contains(day):
            continue
        sink.add("fact_payment_order", {
            "doc_type": "payment_order", "src_id": f"PO-{branch.id:02d}-{ym}-{n:03d}",
            "date_id": date_id(day), "branch_code": branch.code, "item_code": item.code,
            "cp_code": cp, "bank_code": f"ACC-{branch.id:02d}-{bank + 1}", "amount": amount,
            "status": status, "status_date_id": date_id(status_day),
        })
        added += 1
    return added
