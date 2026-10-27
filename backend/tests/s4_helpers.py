"""S4 testlari uchun qo'lda hisoblanadigan ssenariylar (jadvallar — rejaning 4–6-vazifalarida)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.etl.db import etl_transaction
from tests.etl_helpers import branch_row, merge_all, new_tag, open_run, stage
from tests.s1_helpers import rebuild

DONE, ANNOUNCED, EVAL, CANCELLED = "договор заключён", "объявлен", "на оценке", "отменён"


def _branch_id(code: str) -> int:
    with etl_transaction() as conn:
        return int(conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                {"c": code}).scalar_one())


@dataclass(frozen=True, slots=True)
class ProcScenario:
    source: str
    tag: str
    branch_id: int
    branch_code: str
    run_id: int
    build_id: int


def procurement_rows(tag: str) -> dict[str, list[dict[str, Any]]]:
    branch = branch_row(tag)
    code = branch["code"]

    def nom(key: str, subject: str) -> dict[str, Any]:
        return {"code": f"{key}-{tag}", "name": subject, "category": subject, "unit": "—",
                "enbt_code": None}

    def lot(src: str, day: int, method: str, status: str, start: float,
            contract: float | None, days: int | None, sup: str | None,
            subj: str) -> dict[str, Any]:
        return {"doc_type": "portal_lot", "src_id": src, "date_id": day, "branch_code": code,
                "nom_code": f"{subj}-{tag}", "cp_code": f"{sup}-{tag}" if sup else None,
                "lot_no": src.upper(), "method": method, "status": status,
                "start_price": start, "contract_price": contract, "procedure_days": days}

    def plan(src: str, day: int, amount: float) -> dict[str, Any]:
        return {"doc_type": "procurement_plan", "src_id": src, "date_id": day,
                "branch_code": code, "nom_code": None, "cp_code": None, "lot_no": "ПЛАН",
                "method": "plan", "status": "план", "start_price": amount,
                "contract_price": None, "procedure_days": None}

    return {
        "dim_branch": [branch],
        "dim_nomenclature": [nom("SP1", "Запасные части"), nom("SP2", "Ремонтные услуги"),
                             nom("SP3", "Строительно-монтажные работы")],
        "dim_counterparty": [
            {"code": f"S1-{tag}", "name": f"ООО «Поставщик-1 {tag}»", "kind": "supplier",
             "inn": "301111111"},
            {"code": f"S2-{tag}", "name": f"ООО «Поставщик-2 {tag}»", "kind": "supplier",
             "inn": "301111112"}],
        "fact_procurement": [
            lot("l1", 20260810, "eshop", DONE, 100, 90, 12, "S1", "SP1"),
            lot("l2", 20260820, "direct", DONE, 50, 50, 5, "S2", "SP2"),
            lot("l3", 20260905, "tender", DONE, 200, 170, 60, "S1", "SP3"),
            lot("l4", 20260701, "contest", ANNOUNCED, 80, None, None, None, "SP3"),
            lot("l5", 20260910, "eshop", EVAL, 30, None, None, None, "SP1"),
            lot("l6", 20260815, "exchange", CANCELLED, 40, None, None, None, "SP1"),
            lot("l7", 20260210, "eshop", DONE, 60, 57, 10, "S2", "SP1"),
            lot("l8", 20250812, "direct", DONE, 20, 20, 4, "S2", "SP2"),
            plan("p26", 20260101, 1000), plan("p25", 20250101, 500),
        ],
    }


def procurement_scenario(source: str, *, publish: bool = False) -> ProcScenario:
    tag = new_tag()
    run_id = open_run(source)
    stage(run_id, source, procurement_rows(tag))
    merge_all(run_id, source)
    build_id = rebuild(run_id, publish=publish)
    return ProcScenario(source, tag, _branch_id(f"T-{tag}"), f"T-{tag}", run_id, build_id)
