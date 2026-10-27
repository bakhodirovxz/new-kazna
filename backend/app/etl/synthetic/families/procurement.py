"""fact_procurement (lot; yillik reja — 1-yanvar) — prototip «procurement data».

Lot parametrlari (usul, predmet, e'lon kuni, narx, tejash, davomiylik, taqdir) as_of'ga bog'liq
emas; holat as_of bo'yicha: bekor qilingan (6%), tuzilgan (e'lon + davomiylik ≤ as_of), aks holda
«в работе». Oxirgi 75 kundagi lotlarning 30% i «tiqilib qolgan» — kechikkan lotlar demosi.
Yillik reja = yilning barcha lotlari boshlang'ich narxi × 1,4 (prototip `zPlan`).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from app.dwh.dates import date_id, month_id
from app.etl.synthetic.model import SynthModel, money
from app.etl.synthetic.reference import (
    BRANCHES,
    EXPENSE_ITEMS,
    HQ_ID,
    METHOD_PROFILES,
    PROCUREMENT_SUBJECTS,
    SUPPLIER_CODES,
    BranchRef,
    share,
)
from app.etl.synthetic.rng import rnd
from app.etl.types import StagingSink, Window
from app.etl.zakupki.codes import CANCELLED, DONE, IN_WORK, PLAN_DOC, PLAN_METHOD, PLAN_STATUS

LOT_DOC = "synthetic_lot"
_SCALE_ITEMS = ("PKM54-O01", "PKM54-O02", "PKM54-O06", "PKM54-O07")  # prototip exc[0,1,5,6]
_STUCK_DAYS = 75


@dataclass(frozen=True, slots=True)
class Lot:
    branch_id: int
    month: date
    n: int
    method: str
    subject: int
    announce: date
    start: float
    final: float
    dur: int
    cancelled: bool
    stuck: bool
    evaluating: bool
    supplier: str

    @property
    def contract_day(self) -> date:
        return self.announce + timedelta(days=self.dur)


def _scale(branch: BranchRef) -> float:
    return sum(e.base * share(branch, e.hq_share) for e in EXPENSE_ITEMS if e.code in _SCALE_ITEMS)


def lots_for(model: SynthModel, branch: BranchRef, month: date) -> list[Lot]:
    ym = month_id(month)
    r = rnd(model.seed, "lots", branch.id, ym)
    count = r.randint(2, 4) if branch.id == HQ_ID else r.randint(1, 3)
    days = calendar.monthrange(month.year, month.month)[1]
    out: list[Lot] = []
    for n in range(1, count + 1):
        lr = rnd(model.seed, "lot", branch.id, ym, n)
        pick, method = lr.random(), METHOD_PROFILES[-1]
        for profile in METHOD_PROFILES:  # og'irlik bo'yicha tanlash (prototip PMETH)
            if pick < profile[1]:
                method = profile
                break
            pick -= profile[1]
        code, _weight, eco, dur = method
        subject = lr.randrange(len(PROCUREMENT_SUBJECTS))
        start = _scale(branch) * lr.uniform(0.05, 0.45) * (1.8 if subject == 2 else 1.0)
        out.append(Lot(
            branch_id=branch.id, month=month, n=n, method=code, subject=subject,
            announce=month + timedelta(days=lr.randrange(days)), start=start,
            final=start * (1 - lr.uniform(*eco)), dur=lr.randint(*dur),
            cancelled=lr.random() < 0.06, stuck=lr.random() < 0.3,
            evaluating=lr.random() < 0.5, supplier=lr.choice(SUPPLIER_CODES)))
    return out


def lot_state(lot: Lot, as_of: date) -> tuple[str, date] | None:
    if lot.announce > as_of:
        return None
    in_work = IN_WORK[1] if lot.evaluating else IN_WORK[0]
    if lot.cancelled:
        return (CANCELLED, lot.announce) if lot.announce + timedelta(days=5) <= as_of else (
            in_work, lot.announce)
    if lot.stuck and lot.announce >= as_of - timedelta(days=_STUCK_DAYS):
        return in_work, lot.announce
    if lot.contract_day <= as_of:
        return DONE, lot.contract_day
    return in_work, lot.announce


def year_plan(model: SynthModel, branch: BranchRef, year: int) -> float:
    return sum(lot.start for m in range(1, 13)
               for lot in lots_for(model, branch, date(year, m, 1))) * 1.4


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    count = 0
    for branch in BRANCHES:
        for year in range(model.history_start.year, model.as_of.year + 1):
            jan = date(year, 1, 1)
            if window.contains(jan):
                sink.add("fact_procurement", {
                    "doc_type": PLAN_DOC, "src_id": f"PLAN-{branch.id:02d}-{year}",
                    "date_id": date_id(jan), "branch_code": branch.code, "nom_code": None,
                    "cp_code": None, "lot_no": f"ПЛАН-{year}", "method": PLAN_METHOD,
                    "status": PLAN_STATUS, "start_price": money(year_plan(model, branch, year)),
                    "contract_price": None, "procedure_days": None})
                count += 1
        for month in model.months():
            for lot in lots_for(model, branch, month):
                state = lot_state(lot, model.as_of)
                if state is None or not window.contains(state[1]):
                    continue
                status, day = state
                done = status == DONE
                sink.add("fact_procurement", {
                    "doc_type": LOT_DOC,
                    "src_id": f"LOT-{branch.id:02d}-{month_id(month)}-{lot.n}",
                    "date_id": date_id(day), "branch_code": branch.code,
                    "nom_code": f"PS-{lot.subject + 1:02d}",
                    "cp_code": lot.supplier if done else None,
                    "lot_no": f"{month.year}-{branch.id:02d}{month.month:02d}{lot.n}",
                    "method": lot.method, "status": status, "start_price": money(lot.start),
                    "contract_price": money(lot.final) if done else None,
                    "procedure_days": lot.dur if done else None})
                count += 1
    return {"fact_procurement": count}
