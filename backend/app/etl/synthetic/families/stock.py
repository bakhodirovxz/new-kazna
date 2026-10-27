"""fact_stock (oy oxiri / as_of qoldig'i: nomenklatura × ombor) va fact_stock_move (oylik prixod
va rasxod) — prototip «warehouse data»: har filialda 10 (HQ — 6) pozitsiya, minimum ~9% hollarda
buziladi, harakatsiz kunlar 18% hollarda > 180.

`src_id` ichida oy bor: partitsiyalangan faktda bir xil `src_id` boshqa sanada kelsa, 2-reja merge
eski nusxani o'chiradi (hujjat sanasi o'zgargan deb) — oy bilan har oy o'z snapshot'ini saqlaydi.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import timedelta

from app.dwh.dates import date_id, month_id
from app.etl.synthetic.families.production import vol
from app.etl.synthetic.model import SynthModel, money
from app.etl.synthetic.reference import BRANCHES, HQ_ID, NOMENCLATURE, STOCK_CATEGORIES, BranchRef
from app.etl.synthetic.rng import rnd
from app.etl.types import StagingSink, Window

UNIT_QTY: dict[str, tuple[int, int]] = {
    "шт": (5, 80), "м": (200, 4000), "л": (500, 20000), "кг": (500, 15000),
    "компл": (20, 150), "пар": (30, 300),
}
MOVE_DAY = 15


@dataclass(frozen=True, slots=True)
class Position:
    nom: int  # NOMENCLATURE indeksi + 1 (kod NOM-001…)
    name: str
    category: str
    unit: str
    price: float  # mln so'm / birlik
    typical: float
    minimum: int


def warehouse(branch: BranchRef) -> str:
    return "Центральный склад" if branch.id == HQ_ID else f"Склад {branch.short}"


def pool(model: SynthModel, branch: BranchRef) -> list[Position]:
    hq = branch.id == HQ_ID
    picked = sorted(rnd(model.seed, "pool", branch.id).sample(range(len(NOMENCLATURE)),
                                                              6 if hq else 10))
    out: list[Position] = []
    for n in picked:
        name, cat, unit, price = NOMENCLATURE[n]
        r = rnd(model.seed, "typ", branch.id, n)
        lo, hi = UNIT_QTY[unit]
        typical = r.uniform(lo, hi) * (0.5 if hq else branch.weight)
        out.append(Position(n + 1, name, STOCK_CATEGORIES[cat], unit, price, typical,
                            round(typical * r.uniform(0.35, 0.7))))
    return out


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    stock_rows = move_rows = 0
    for branch in BRANCHES:
        wh = warehouse(branch)
        for pos in pool(model, branch):
            code = f"NOM-{pos.nom:03d}"
            for month in model.months():
                end = model.period_end(month)
                ym = month_id(month)
                r = rnd(model.seed, "stock", branch.id, pos.nom, ym)
                if r.random() < 0.09:
                    qty = round(pos.minimum * r.uniform(0.15, 0.9))
                else:
                    qty = round(pos.typical * r.uniform(0.8, 1.6))
                roll = r.random()
                age = (r.randint(181, 720) if roll < 0.18
                       else r.randint(91, 180) if roll < 0.43 else r.randint(1, 90))
                value = qty * pos.price
                if window.contains(end):
                    sink.add("fact_stock", {
                        "doc_type": "stock_snapshot",
                        "src_id": f"ST-{branch.id:02d}-{pos.nom:03d}-{ym}",
                        "date_id": date_id(end), "branch_code": branch.code, "nom_code": code,
                        "warehouse": wh, "qty": vol(qty), "value": money(value),
                        "min_qty": vol(pos.minimum),
                        "last_move_date_id": date_id(end - timedelta(days=age))})
                    stock_rows += 1
                day = min(month.replace(day=MOVE_DAY), end)
                part = end.day / calendar.monthrange(month.year, month.month)[1]
                if not window.contains(day):
                    continue
                for direction, lo, hi in (("in", 0.12, 0.22), ("out", 0.13, 0.21)):
                    amount = value * r.uniform(lo, hi) * part
                    if amount < 0.01:
                        continue
                    sink.add("fact_stock_move", {
                        "doc_type": "stock_move",
                        "src_id": f"SM-{branch.id:02d}-{pos.nom:03d}-{ym}-{direction}",
                        "date_id": date_id(day), "branch_code": branch.code, "nom_code": code,
                        "direction": direction, "qty": vol(amount / pos.price),
                        "value": money(amount)})
                    move_rows += 1
    return {"fact_stock": stock_rows, "fact_stock_move": move_rows}
