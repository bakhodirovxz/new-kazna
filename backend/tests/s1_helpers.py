"""S1 testlari uchun qo'lda hisoblanadigan g'aznachilik ssenariysi (jadval — rejaning 3-vazifasida).

Har test o'z `src_system` va test filiali bilan ishlaydi; `purge_source(source)` o'chiradi.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text

from app.dwh import builds
from app.dwh.aggregates import BuildParams, build_all
from app.dwh.targets import SCHEDULE_DOC_TYPE
from app.etl.db import etl_transaction
from tests.etl_helpers import TEST_AS_OF, branch_row, merge_all, new_tag, open_run, stage

SCENARIO_PARAMS = BuildParams(as_of=TEST_AS_OF, date_from=date(2025, 1, 1))
IN_ITEM, OUT_ITEM = "PKM54-I06", "PKM54-O09"


@dataclass(frozen=True, slots=True)
class Scenario:
    source: str
    tag: str
    branch_id: int
    branch_code: str
    run_id: int
    build_id: int
    item_out_id: int
    item_in_id: int


def _cash(src: str, day: int, branch: str, amount: float, direction: str, bank: str,
          **extra: Any) -> dict[str, Any]:
    return {"doc_type": "bank_entry", "src_id": src, "date_id": day, "branch_code": branch,
            "item_code": IN_ITEM if direction == "in" else OUT_ITEM, "direction": direction,
            "amount": amount, "gl_account": "5110", "bank_code": bank, **extra}


def scenario_rows(tag: str) -> dict[str, list[dict[str, Any]]]:
    branch = branch_row(tag)
    code = branch["code"]
    bank_a, bank_b = f"ACC-{tag}-A", f"ACC-{tag}-B"
    cp, ct1, ct2 = f"CP-{tag}", f"CT-{tag}-1", f"CT-{tag}-2"
    src, loan = f"S-{tag}", f"LOAN-{tag}"

    def bal(src_id: str, day: int, bank: str, value: float) -> dict[str, Any]:
        return {"doc_type": "statement", "src_id": src_id, "date_id": day, "branch_code": code,
                "bank_code": bank, "balance": value}

    def plan(src_id: str, day: int, amount: float,
             doc_type: str = "payment_plan") -> dict[str, Any]:
        return {"doc_type": doc_type, "src_id": src_id, "date_id": day, "branch_code": code,
                "item_code": OUT_ITEM, "amount": amount}

    def order(src_id: str, day: int, amount: float, status: str) -> dict[str, Any]:
        return {"doc_type": "payment_order", "src_id": src_id, "date_id": day,
                "branch_code": code, "item_code": OUT_ITEM, "cp_code": cp, "bank_code": bank_b,
                "amount": amount, "status": status, "status_date_id": day}

    return {
        "dim_branch": [branch],
        "dim_bank": [
            {"code": bank_a, "bank_name": f"Тест-банк А {tag}", "account_number": f"2021{tag}1",
             "currency": "UZS"},
            {"code": bank_b, "bank_name": f"Тест-банк Б {tag}", "account_number": f"2021{tag}2",
             "currency": "UZS"},
        ],
        "dim_counterparty": [{"code": cp, "name": f"ООО «Тест Поставщик {tag}»",
                              "kind": "supplier", "inn": "301234567"}],
        "dim_contract": [
            {"code": ct1, "number": f"№ 1/{tag}", "contract_date": "2025-01-10", "amount": 100,
             "end_date": "2026-12-31", "kind": "payable", "branch_code": code, "cp_code": cp},
            {"code": ct2, "number": f"№ 2/{tag}", "contract_date": "2025-02-01", "amount": 50,
             "end_date": "2026-06-30", "kind": "receivable", "branch_code": code, "cp_code": cp},
        ],
        "dim_source": [{"code": src, "name": f"Тестовый источник {tag}", "kind": "own"}],
        "dim_loan": [{"code": loan, "creditor": "Тест кредитор", "project": "Тест проект",
                      "currency": "XTS", "rate": 0.04, "grace_until": "2026-01-01",
                      "maturity": "2030-12-31", "amount_uzs": 1000, "branch_code": code}],
        "fx_rate": [{"currency": "XTS", "date_id": 20260901, "rate": 1000}],
        "fact_cashflow": [
            _cash("c1", 20260810, code, 100, "in", bank_a),
            _cash("c2", 20260811, code, 40, "out", bank_b, cp_code=cp, contract_code=ct1),
            _cash("c3", 20260910, code, 30, "in", bank_a),
            _cash("c4", 20260920, code, 12, "out", bank_b),
            _cash("ly1", 20250905, code, 9, "in", bank_a),
            _cash("ly2", 20250920, code, 7, "out", bank_b),
            _cash("ly3", 20250928, code, 5, "out", bank_b),
        ],
        "fact_balance": [
            bal("ba1", 20250831, bank_a, 450), bal("ba2", 20250920, bank_a, 455),
            bal("ba3", 20250930, bank_a, 459), bal("ba4", 20260731, bank_a, 600),
            bal("ba5", 20260831, bank_a, 700), bal("ba6", 20260924, bank_a, 730),
            bal("bb1", 20250831, bank_b, 300), bal("bb2", 20250930, bank_b, 288),
            bal("bb3", 20260731, bank_b, 400), bal("bb4", 20260831, bank_b, 360),
            bal("bb5", 20260924, bank_b, 348),
        ],
        "fact_payment_plan": [
            plan("p1", 20260801, 50), plan("p2", 20260901, 30),
            plan("s1", 20260925, 6, SCHEDULE_DOC_TYPE), plan("s2", 20261001, 4, SCHEDULE_DOC_TYPE),
            plan("s3", 20261009, 3, SCHEDULE_DOC_TYPE),
        ],
        "fact_payment_order": [
            order("o1", 20260812, 10, "исполнено"), order("o2", 20260813, 5, "исполнено"),
            order("o3", 20260814, 2, "отклонено"), order("o4", 20260915, 8, "на согласовании"),
            order("o5", 20260916, 3, "утверждено"),
        ],
        "fact_debt": [
            {"doc_type": "debt_snapshot", "src_id": "d1", "date_id": 20260831, "branch_code": code,
             "contract_code": ct1, "cp_code": cp, "receivable": 0, "payable": 100, "overdue": 0,
             "overdue_days": 0},
            {"doc_type": "debt_snapshot", "src_id": "d2", "date_id": 20260924, "branch_code": code,
             "contract_code": ct1, "cp_code": cp, "receivable": 0, "payable": 120, "overdue": 60,
             "overdue_days": 95},
            {"doc_type": "debt_snapshot", "src_id": "d3", "date_id": 20260831, "branch_code": code,
             "contract_code": ct2, "cp_code": cp, "receivable": 50, "payable": 0, "overdue": 10,
             "overdue_days": 20},
        ],
        "fact_target_funds": [
            {"doc_type": "target_funds", "src_id": "tf1", "date_id": 20260801, "branch_code": code,
             "source_code": src, "allocated": 10, "used": 4},
            {"doc_type": "target_funds", "src_id": "tf2", "date_id": 20260901, "branch_code": code,
             "source_code": src, "allocated": 10, "used": 6},
        ],
        "fact_loan_schedule": [
            {"doc_type": "loan_schedule", "src_id": "l1", "date_id": 20261002, "branch_code": code,
             "loan_code": loan, "principal": 0.1, "interest": 0.02, "balance": 1},
            {"doc_type": "loan_schedule", "src_id": "l2", "date_id": 20261201, "branch_code": code,
             "loan_code": loan, "principal": 0.1, "interest": 0.02, "balance": 0.9},
        ],
    }


def rebuild(run_id: int, *, publish: bool = False) -> int:
    with etl_transaction() as conn:
        build_id = builds.create_build(conn, run_id)
        build_all(conn, build_id, SCENARIO_PARAMS)
        builds.mark_ready(conn, build_id)
        if publish:
            builds.publish(conn, build_id, keep=3)
    return build_id


def treasury_scenario(source: str, *, publish: bool = False) -> Scenario:
    tag = new_tag()
    run_id = open_run(source)
    stage(run_id, source, scenario_rows(tag))
    merge_all(run_id, source)
    build_id = rebuild(run_id, publish=publish)
    with etl_transaction() as conn:
        branch_id = int(conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                     {"c": f"T-{tag}"}).scalar_one())
        items = dict(conn.execute(text(
            "SELECT code, item_id FROM dwh.dim_item WHERE code IN (:i, :o)"),
            {"i": IN_ITEM, "o": OUT_ITEM}).all())
    return Scenario(source, tag, branch_id, f"T-{tag}", run_id, build_id, int(items[OUT_ITEM]),
                    int(items[IN_ITEM]))
