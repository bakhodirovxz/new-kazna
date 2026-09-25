from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest

from app.etl.db import etl_transaction
from app.etl.quality import CHECK_CODES, CheckResult, failed, run_checks
from app.etl.types import ControlTotals
from tests.etl_helpers import (
    FULL_WINDOW,
    branch_row,
    cash_row,
    load_and_build,
    new_source,
    new_tag,
    purge_source,
)


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def _check(source: str, rows: dict[str, list[dict[str, Any]]],
           totals: ControlTotals | None = None) -> dict[str, CheckResult]:
    run_id, build_id = load_and_build(source, rows)
    with etl_transaction() as conn:
        results = run_checks(conn, run_id=run_id, build_id=build_id, source=source,
                             window=FULL_WINDOW, totals=totals)
    assert [r.code for r in results] == list(CHECK_CODES)
    return {r.code: r for r in results}


def _clean(tag: str, **branch: Any) -> dict[str, list[dict[str, Any]]]:
    b = branch_row(tag, **branch)
    return {"dim_branch": [b],
            "fact_cashflow": [cash_row("c1", 20260805, b["code"], 100),
                              cash_row("c2", 20260906, b["code"], 50, direction="in",
                                       item_code="PKM54-I06")]}


def test_clean_data_passes_all_checks(source: str) -> None:
    results = _check(source, _clean(new_tag()),
                     ControlTotals({202608: Decimal("100"), 202609: Decimal("50")}))
    assert failed(list(results.values())) == []


def test_control_totals_mismatch_fails(source: str) -> None:
    results = _check(source, _clean(new_tag()),
                     ControlTotals({202608: Decimal("101"), 202609: Decimal("50")}))
    assert not results["control_totals"].ok
    assert results["control_totals"].detail["mismatches"][0]["month"] == 202608


def test_control_totals_within_tolerance_pass(source: str) -> None:
    results = _check(source, _clean(new_tag()),
                     ControlTotals({202608: Decimal("100.05"), 202609: Decimal("50")}))
    assert results["control_totals"].ok


def test_missing_month_in_source_totals_fails(source: str) -> None:
    results = _check(source, _clean(new_tag()), ControlTotals({202608: Decimal("100")}))
    assert not results["control_totals"].ok


def test_balance_identity_violation_fails(source: str) -> None:
    tag = new_tag()
    rows = _clean(tag)
    code = rows["dim_branch"][0]["code"]
    rows["dim_bank"] = [{"code": f"ACC-{tag}", "bank_name": "Тест", "currency": "UZS"}]
    rows["fact_balance"] = [
        {"doc_type": "statement", "src_id": "o", "date_id": 20260731, "branch_code": code,
         "bank_code": f"ACC-{tag}", "balance": 1000},
        # To'g'risi 900 (1000 − 100); 800 — farq 100, oborot 100 ning 1% idan katta.
        {"doc_type": "statement", "src_id": "c", "date_id": 20260831, "branch_code": code,
         "bank_code": f"ACC-{tag}", "balance": 800},
        {"doc_type": "statement", "src_id": "s", "date_id": 20260924, "branch_code": code,
         "bank_code": f"ACC-{tag}", "balance": 850},
    ]
    results = _check(source, rows)
    assert not results["balance_identity"].ok
    assert results["balance_identity"].detail["violations"][0]["month_id"] == 202608


def test_balance_identity_small_difference_passes(source: str) -> None:
    tag = new_tag()
    rows = _clean(tag)
    code = rows["dim_branch"][0]["code"]
    rows["dim_bank"] = [{"code": f"ACC-{tag}", "bank_name": "Тест", "currency": "UZS"}]
    rows["fact_balance"] = [
        {"doc_type": "statement", "src_id": "o", "date_id": 20260731, "branch_code": code,
         "bank_code": f"ACC-{tag}", "balance": 1000},
        {"doc_type": "statement", "src_id": "c", "date_id": 20260831, "branch_code": code,
         "bank_code": f"ACC-{tag}", "balance": 899.5},  # |Разница| 0,5 ≤ 1% × 100
        {"doc_type": "statement", "src_id": "s", "date_id": 20260924, "branch_code": code,
         "bank_code": f"ACC-{tag}", "balance": 949.5},  # sentabr: +50 kirim
    ]
    assert _check(source, rows)["balance_identity"].ok


def test_missing_branch_fails_mandatory_dims(source: str) -> None:
    rows = _clean(new_tag())
    rows["fact_cashflow"].append(cash_row("x", 20260805, "NO-BRANCH", 5))
    results = _check(source, rows)
    assert not results["mandatory_dims"].ok
    assert results["mandatory_dims"].detail["errors"] == 1


def test_unknown_item_only_warns(source: str) -> None:
    rows = _clean(new_tag())
    rows["fact_cashflow"].append(
        cash_row("y", 20260805, rows["dim_branch"][0]["code"], 5, item_code="NO-ITEM"))
    results = _check(source, rows)
    assert results["mandatory_dims"].ok
    assert results["mandatory_dims"].detail["warnings"] == 1


def test_generation_above_capacity_fails(source: str) -> None:
    tag = new_tag()
    rows = _clean(tag, capacity_mw=10)  # maksimum 10 × 24 = 240 MVt·soat = 0,24 mln kVt·soat
    code = rows["dim_branch"][0]["code"]
    rows["fact_generation"] = [
        {"doc_type": "askue_day", "src_id": "g1", "date_id": 20260805, "branch_code": code,
         "generation": 0.2},
        {"doc_type": "askue_day", "src_id": "g2", "date_id": 20260806, "branch_code": code,
         "generation": 0.5},
    ]
    results = _check(source, rows)
    assert not results["capacity_limit"].ok
    assert [v["date_id"] for v in results["capacity_limit"].detail["violations"]] == [20260806]


def test_missing_counterparty_fails_dangling_refs(source: str) -> None:
    rows = _clean(new_tag())
    rows["fact_cashflow"].append(
        cash_row("z", 20260805, rows["dim_branch"][0]["code"], 5, cp_code="NO-CP"))
    results = _check(source, rows)
    assert not results["dangling_refs"].ok
    assert results["dangling_refs"].detail["errors"] == 1
