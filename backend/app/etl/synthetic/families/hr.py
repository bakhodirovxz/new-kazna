"""fact_hr (filial × toifa × oy; sana — oy oxiri yoki as_of) — prototip «HR data».

Штат: HQ 182, stansiyalar 40 + quvvat / 5 + vazn × 45; fakt = штат × (0,86–1,0); toifalar ulushi
prototip HSH. Qabul/bo'shatish/ish vaqtidan tashqari soatlar oylik, joriy oyda o'tgan kunlar ulushi.
ФОТ bu yerda 0 — ko'rsatkich pul oqimidan (PKM54-O05) olinadi (S4 spec 3.3). ФИО yo'q.
"""

from __future__ import annotations

import calendar
from decimal import Decimal

from app.dwh.dates import date_id, month_id
from app.etl.synthetic.model import SynthModel
from app.etl.synthetic.reference import BRANCHES, HQ_ID, POSITIONS, BranchRef
from app.etl.synthetic.rng import rnd
from app.etl.types import StagingSink, Window

HR_DOC = "hr_month"
SHARES = (0.08, 0.22, 0.42, 0.28)


def staff(model: SynthModel, branch: BranchRef) -> tuple[int, int]:
    plan = 182 if branch.id == HQ_ID else round(40 + (branch.capacity or 60) / 5
                                                 + branch.weight * 45)
    return plan, round(plan * rnd(model.seed, "hrfill", branch.id).uniform(0.86, 1.0))


def split(total: int) -> list[int]:
    parts = [round(total * s) for s in SHARES[:-1]]
    return [*parts, total - sum(parts)]


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    count = 0
    for branch in BRANCHES:
        plan, fact = staff(model, branch)
        plans, facts = split(plan), split(fact)
        for month in model.months():
            end = model.period_end(month)
            if not window.contains(end):
                continue
            part = end.day / calendar.monthrange(month.year, month.month)[1]
            for i, (pos, _cat, _dep) in enumerate(POSITIONS):
                r = rnd(model.seed, "hr", branch.id, i, month_id(month))
                people = facts[i]
                sink.add("fact_hr", {
                    "doc_type": HR_DOC, "src_id": f"HR-{branch.id:02d}-{i + 1}-{month_id(month)}",
                    "date_id": date_id(end), "branch_code": branch.code, "pos_code": pos,
                    "headcount_plan": Decimal(plans[i]), "headcount_fact": Decimal(people),
                    "payroll": Decimal("0.00"),
                    "hired": round(r.uniform(0, people * 0.012) * part),
                    "fired": round(r.uniform(0, people * 0.014) * part),
                    "overtime_hours": Decimal(f"{people * r.uniform(0.4, 1.8) * part:.1f}")})
                count += 1
    return {"fact_hr": count}
