"""Barcha o'lchovlar (oyna ularga ta'sir qilmaydi — har yuklashda to'liq).

Sintetik identifikatorlar haqiqiyisi bilan adashtirilmasligi shart (reserved synthetic
prefix — haqiqiy tayinlangan oraliq EMAS): INN `999…` (9 raqam; filiallar `999000NNN`,
kontragentlar `999` + 6 raqamli hisoblagich), bank hisobi `99999000…` (20 raqam, `99999` —
mavjud bo'lmagan balans hisobi kodi). Kontragent/bank NOMLARI prototipdagi kabi real
muassasalarga o'xshaydi — sintetik manba (`src_system = 'synthetic'`) INN/hisob bo'yicha
qidiruvlarga (blind-index) kirmaydi: bugungi kunda bidx bo'yicha qidiruv mavjud emas
(faqat merge'dagi o'zgarish aniqlash), kelajakda qo'shilsa `src_system <> 'synthetic'`
bilan filtrlansin."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from app.etl.synthetic.model import SynthModel, money
from app.etl.synthetic.reference import (
    BANKS,
    BRANCH_BY_ID,
    BRANCHES,
    EXPENSE_ITEMS,
    FUNDS,
    INCOME_ITEMS,
    LOANS,
    NOMENCLATURE,
    OBJECTS,
    OTHER_COUNTERPARTIES,
    POSITIONS,
    STOCK_CATEGORIES,
    SUPPLIER_CODES,
    SUPPLIERS,
    WORK_TYPES,
)
from app.etl.types import StagingSink, Window


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    counts: dict[str, int] = {}

    def emit(target: str, rows: Sequence[Mapping[str, Any]]) -> None:
        for row in rows:
            sink.add(target, row)
        counts[target] = len(rows)

    emit("dim_branch", [
        {"code": b.code, "name": b.name, "short_name": b.short, "inn": f"999000{b.id:03d}",
         "kind": b.kind, "capacity_mw": b.capacity, "lat": b.lat, "lon": b.lon,
         "sort_order": b.id}
        for b in BRANCHES
    ])
    emit("dim_item", [
        {"code": i.code, "name": i.name, "activity": i.activity, "direction": i.direction,
         "sort_order": (100 if i.direction == "in" else 200) + n}
        for items in (INCOME_ITEMS, EXPENSE_ITEMS) for n, i in enumerate(items, start=1)
    ])
    counterparties = [(c, n, "supplier") for c, n in zip(SUPPLIER_CODES, SUPPLIERS, strict=True)]
    counterparties += list(OTHER_COUNTERPARTIES)
    emit("dim_counterparty", [
        {"code": code, "name": name, "kind": kind, "inn": f"999{n:06d}"}
        for n, (code, name, kind) in enumerate(counterparties, start=1)
    ])
    emit("dim_bank", [
        {"code": f"ACC-{b.id:02d}-{k + 1}", "bank_name": bank, "currency": "UZS",
         "account_number": f"99999000{n:012d}"}
        for n, (b, k, bank) in enumerate(
            ((b, k, bank) for b in BRANCHES for k, bank in enumerate(BANKS)), start=1)
    ])
    emit("dim_nomenclature", [
        {"code": f"NOM-{n:03d}", "name": name, "category": STOCK_CATEGORIES[cat], "unit": unit,
         "enbt_code": f"ЕНБТ-{cat + 1:02d}-{n:03d}"}
        for n, (name, cat, unit, _price) in enumerate(NOMENCLATURE, start=1)
    ])
    emit("dim_source", [{"code": c, "name": n, "kind": k} for c, n, k in FUNDS])
    emit("dim_object", [
        {"code": f"OBJ-{n:02d}", "name": name, "program_code": f"АИП-{deadline}-{n:02d}",
         "work_type": WORK_TYPES[kind], "commissioning_year": deadline,
         "total_cost": money(total * 1000), "source_code": FUNDS[src][0]}
        for n, (name, _b, kind, src, total, _plan, deadline) in enumerate(OBJECTS, start=1)
    ])
    emit("dim_contract", [
        {"code": c.code, "number": c.number, "contract_date": c.contract_date,
         "amount": c.amount, "end_date": c.end_date, "kind": c.kind,
         "branch_code": BRANCH_BY_ID[c.branch_id].code, "cp_code": c.cp_code,
         "object_code": c.object_code}
        for c in model.contracts
    ])
    emit("dim_loan", [
        {"code": f"LOAN-{n:02d}", "creditor": creditor, "project": project, "currency": cur,
         "rate": rate, "grace_until": date(grace, 1, 1), "maturity": date(end, 12, 31),
         "amount_uzs": money(amount * 1000), "branch_code": BRANCHES[b].code}
        for n, (creditor, project, b, cur, amount, rate, grace, end) in enumerate(LOANS, start=1)
    ])
    emit("dim_position", [{"code": c, "category": cat, "department": dep}
                          for c, cat, dep in POSITIONS])
    return counts
