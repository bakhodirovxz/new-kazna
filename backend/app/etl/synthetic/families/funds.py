"""fact_target_funds: manba × oy × filial — ajratilgan va ishlatilgan (prototip `funds`)."""

from __future__ import annotations

from app.dwh.dates import date_id, month_id
from app.etl.synthetic.model import SynthModel, money
from app.etl.synthetic.reference import BRANCHES, EXPENSE_ITEMS, FUNDS, HQ_ID, share
from app.etl.synthetic.rng import rnd
from app.etl.types import StagingSink, Window


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    count = 0
    for branch in BRANCHES:
        monthly_out = sum(e.base * share(branch, e.hq_share) for e in EXPENSE_ITEMS)
        for n, (code, _name, _kind) in enumerate(FUNDS, start=1):
            r = rnd(model.seed, "fund", branch.id, n)
            if not (n == 4 or r.random() > 0.45):
                continue
            allocated = monthly_out * r.uniform(0.8, 3) * (2.5 if branch.id == HQ_ID else 1) / 12
            for month in model.months():
                if not window.contains(month):
                    continue
                ym = month_id(month)
                used = allocated * rnd(model.seed, "fund", branch.id, n, ym).uniform(0.55, 0.97)
                sink.add("fact_target_funds", {
                    "doc_type": "target_funds", "src_id": f"TF-{branch.id:02d}-{n}-{ym}",
                    "date_id": date_id(month), "branch_code": branch.code, "source_code": code,
                    "allocated": money(allocated), "used": money(used),
                })
                count += 1
    return {"fact_target_funds": count}
