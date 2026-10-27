"""fact_generation (stansiya × sutka; oylik reja — oyning 1-kuni) va fact_energy_sales
(filial × xaridor × oy) — prototip «production data»: quvvat × 24 × oylik КИУМ × tebranish.

Birliklar: mln kVt·soat; realizatsiya — mln so'm (mln kVt·soat × so'm/kVt·soat).
Sutkalik ishlab chiqarish har doim ≤ quvvat × 24 (sifat tekshiruvi 4): 0,62 × 1,08 × 1,1 < 1.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from app.dwh.dates import date_id, month_id
from app.etl.synthetic.model import SynthModel, money
from app.etl.synthetic.reference import BRANCHES, BranchRef
from app.etl.synthetic.rng import rnd
from app.etl.types import StagingSink, Window

# Oylik КИУМ: prototip CF (yanvar…sentabr) + kuzgi kam suvli oylar.
CF = (0.28, 0.27, 0.33, 0.42, 0.55, 0.62, 0.60, 0.52, 0.40, 0.33, 0.30, 0.29)
GEN_YEAR = {2024: 0.88, 2025: 0.93}  # 2026 = 1,0 (prototip gen25 ≈ rejaning 0,82–1,0)
BUYERS = (("CP-013", 0.85), ("CP-014", 0.15))
PLAN_DOC = "generation_plan"
DAILY_DOC = "synthetic_daily"


def tariff(day: date) -> float:
    """So'm / kVt·soat (prototip TARIFF: 1-yarim yil 655, keyin 705; oldingi yillar arzonroq)."""
    base = 655.0 if day.month <= 6 else 705.0
    return base * {2024: 0.8, 2025: 0.9}.get(day.year, 1.0)


def vol(value: float) -> Decimal:
    return Decimal(f"{value:.3f}")


def stations() -> list[BranchRef]:
    return [b for b in BRANCHES if b.kind in ("ges", "cascade") and b.capacity]


def daily(model: SynthModel, branch: BranchRef, day: date) -> tuple[float, float, float]:
    capacity = branch.capacity or 0
    eff = rnd(model.seed, "eff", branch.id).uniform(0.9, 1.08)
    r = rnd(model.seed, "gen", branch.id, date_id(day))
    gen = (capacity * 24 * CF[day.month - 1] * eff * GEN_YEAR.get(day.year, 1.0)
           * r.uniform(0.9, 1.1) / 1000)
    return gen, gen * r.uniform(0.012, 0.02), 24 * r.uniform(0.85, 1.0)


def monthly_plan(model: SynthModel, branch: BranchRef, month: date) -> float:
    days = calendar.monthrange(month.year, month.month)[1]
    r = rnd(model.seed, "genplan", branch.id, month_id(month))
    return ((branch.capacity or 0) * 24 * days * CF[month.month - 1]
            * GEN_YEAR.get(month.year, 1.0) * r.uniform(0.97, 1.04) / 1000)


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    gen_rows = sales_rows = 0
    for branch in stations():
        for month in model.months():
            end = model.period_end(month)
            supply = 0.0
            day = month
            while day <= end:
                gen, own, hours = daily(model, branch, day)
                supply += gen - own
                if window.contains(day):
                    sink.add("fact_generation", {
                        "doc_type": DAILY_DOC, "src_id": f"GEN-{branch.id:02d}-{date_id(day)}",
                        "date_id": date_id(day), "branch_code": branch.code,
                        "generation": vol(gen), "own_needs": vol(own), "supply": vol(gen - own),
                        "plan": None, "work_hours": Decimal(f"{hours:.2f}")})
                    gen_rows += 1
                day += timedelta(days=1)
            if window.contains(month):
                # Oylik reja — oyning 1-kuni (spec 3.1); ochiq oyda agregat ulush bilan oladi.
                sink.add("fact_generation", {
                    "doc_type": PLAN_DOC, "src_id": f"PLAN-{branch.id:02d}-{month_id(month)}",
                    "date_id": date_id(month), "branch_code": branch.code,
                    "generation": Decimal("0.000"), "own_needs": Decimal("0.000"),
                    "supply": Decimal("0.000"), "plan": vol(monthly_plan(model, branch, month)),
                    "work_hours": None})
                gen_rows += 1
            if window.contains(end):
                accrued = supply * tariff(month)
                level = rnd(model.seed, "sales", branch.id, month_id(month)).uniform(0.8, 1.03)
                for cp, share in BUYERS:
                    sink.add("fact_energy_sales", {
                        "doc_type": "energy_sales",
                        "src_id": f"ES-{branch.id:02d}-{cp}-{month_id(month)}",
                        "date_id": date_id(end), "branch_code": branch.code, "cp_code": cp,
                        "accrued": money(accrued * share), "paid": money(accrued * share * level),
                        "volume": vol(supply * share)})
                    sales_rows += 1
    return {"fact_generation": gen_rows, "fact_energy_sales": sales_rows}
