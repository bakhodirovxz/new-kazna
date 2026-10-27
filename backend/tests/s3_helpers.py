"""S3 testlari uchun qo'lda hisoblanadigan ssenariylar (jadvallar — rejaning 3–4-vazifalarida)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.etl.db import etl_transaction
from tests.etl_helpers import branch_row, merge_all, new_tag, open_run, stage
from tests.s1_helpers import rebuild


@dataclass(frozen=True, slots=True)
class ProdScenario:
    source: str
    tag: str
    branch_id: int
    branch_code: str
    hq_id: int
    run_id: int
    build_id: int


def production_rows(tag: str) -> dict[str, list[dict[str, Any]]]:
    station = branch_row(tag, capacity_mw=100)
    hq = branch_row(f"{tag}H", name=f"Тестовая головная {tag}", kind="head", capacity_mw=None)
    code = station["code"]
    buyer = f"CPB-{tag}"

    def gen(src_id: str, day: int, value: float, own: float) -> dict[str, Any]:
        return {"doc_type": "askue_daily", "src_id": src_id, "date_id": day, "branch_code": code,
                "generation": value, "own_needs": own, "supply": round(value - own, 3),
                "plan": None, "work_hours": 24}

    def plan(src_id: str, day: int, value: float) -> dict[str, Any]:
        return {"doc_type": "generation_plan", "src_id": src_id, "date_id": day,
                "branch_code": code, "generation": 0, "own_needs": 0, "supply": 0,
                "plan": value, "work_hours": None}

    def sale(src_id: str, day: int, accrued: float, paid: float) -> dict[str, Any]:
        return {"doc_type": "energy_sales", "src_id": src_id, "date_id": day,
                "branch_code": code, "cp_code": buyer, "accrued": accrued, "paid": paid,
                "volume": 1}

    return {
        "dim_branch": [station, hq],
        "dim_counterparty": [{"code": buyer, "name": f"Тест покупатель {tag}", "kind": "buyer",
                              "inn": "301234567"}],
        "fact_generation": [
            gen("g1", 20260810, 1.0, 0.02), gen("g2", 20260820, 0.8, 0.02),
            gen("g3", 20260905, 0.6, 0.01), gen("g4", 20260920, 0.4, 0.01),
            gen("p1", 20250815, 1.5, 0.03), gen("p2", 20250910, 0.5, 0.01),
            gen("p3", 20250928, 0.7, 0.01),
            plan("pl1", 20260801, 2.0), plan("pl2", 20260901, 1.5), plan("pl3", 20250901, 1.2),
        ],
        "fact_energy_sales": [sale("s1", 20260831, 1200, 900), sale("s2", 20260924, 500, 450)],
    }


def production_scenario(source: str, *, publish: bool = False) -> ProdScenario:
    tag = new_tag()
    run_id = open_run(source)
    stage(run_id, source, production_rows(tag))
    merge_all(run_id, source)
    build_id = rebuild(run_id, publish=publish)
    with etl_transaction() as conn:
        ids = dict(conn.execute(text(
            "SELECT code, branch_id FROM dwh.dim_branch WHERE code IN (:a, :b)"),
            {"a": f"T-{tag}", "b": f"T-{tag}H"}).all())
    return ProdScenario(source, tag, int(ids[f"T-{tag}"]), f"T-{tag}", int(ids[f"T-{tag}H"]),
                        run_id, build_id)
