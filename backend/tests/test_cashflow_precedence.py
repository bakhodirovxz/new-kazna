from collections.abc import Callable, Iterator
from datetime import date
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import new_session
from app.etl.db import etl_transaction
from app.etl.quality import run_checks
from app.etl.staging import DbStagingSink
from app.etl.types import ReportingSink, Window
from tests.etl_helpers import (
    TEST_AS_OF,
    branch_row,
    cash_row,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)
from tests.helpers import put_setting
from tests.s1_helpers import rebuild


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


@pytest.fixture
def statement_branches() -> Iterator[Callable[[list[str]], None]]:
    def put(codes: list[str]) -> None:
        put_setting("banks.statement_branches", codes)

    yield put
    put([])


def _load(source: str, *, balances: bool = False) -> tuple[str, int, int]:
    tag = new_tag()
    branch = branch_row(tag)
    code = branch["code"]
    rows: dict[str, list[dict[str, Any]]] = {
        "dim_branch": [branch],
        "fact_cashflow": [
            cash_row("c1", 20260805, code, 50, doc_type="onec_payment"),
            cash_row("c2", 20260806, code, 45, doc_type="bank_statement"),
            cash_row("c3", 20260807, code, 5),  # boshqa manba (bank_entry) — doim hisobga olinadi
        ],
    }
    if balances:
        rows["dim_bank"] = [{"code": f"BA-{tag}", "bank_name": "Тест-банк",
                             "account_number": f"2021{tag}", "currency": "UZS"}]
        rows["fact_balance"] = [
            {"doc_type": "bank_balance", "src_id": "b1", "date_id": 20260731,
             "branch_code": code, "bank_code": f"BA-{tag}", "balance": 1000},
            {"doc_type": "bank_balance", "src_id": "b2", "date_id": 20260831,
             "branch_code": code, "bank_code": f"BA-{tag}", "balance": 500},
        ]
    run = open_run(source)
    stage(run, source, rows)
    merge_all(run, source)
    with etl_transaction() as conn:
        branch_id = int(conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                     {"c": code}).scalar_one())
    return code, branch_id, run


def _outflows(build_id: int, branch_id: int) -> tuple[float, float, float]:
    with etl_transaction() as conn:
        cash = conn.execute(text(
            "SELECT outflow FROM mart.agg_cash_month WHERE build_id = :b AND branch_id = :br "
            "AND month_id = 202608 AND item_id = 0"), {"b": build_id, "br": branch_id}).scalar_one()
        fact = conn.execute(text(
            "SELECT sum(fact_amount) FROM mart.agg_payments_month WHERE build_id = :b "
            "AND branch_id = :br AND month_id = 202608"),
            {"b": build_id, "br": branch_id}).scalar_one()
        banks = conn.execute(text(
            "SELECT sum(outflow) FROM mart.agg_cash_bank_month WHERE build_id = :b "
            "AND branch_id = :br AND month_id = 202608"),
            {"b": build_id, "br": branch_id}).scalar_one()
    return float(cash), float(fact), float(banks)


def test_default_uses_onec_not_statement(source: str) -> None:
    _code, branch_id, run = _load(source)
    assert _outflows(rebuild(run), branch_id) == (55.0, 55.0, 55.0)


def test_statement_branch_uses_bank_lines_only(
        source: str, statement_branches: Callable[[list[str]], None]) -> None:
    code, branch_id, run = _load(source)
    statement_branches([code])
    assert _outflows(rebuild(run), branch_id) == (50.0, 50.0, 50.0)


def _identity_branches(run: int, build_id: int, source: str) -> set[int]:
    with etl_transaction() as conn:
        results = run_checks(conn, run_id=run, build_id=build_id, source=source,
                             window=Window(date(2026, 8, 1), TEST_AS_OF), totals=None)
    identity = next(r for r in results if r.code == "balance_identity")
    return {v["branch_id"] for v in identity.detail["violations"]}


def test_balance_identity_skipped_for_cross_source_branch(
        source: str, statement_branches: Callable[[list[str]], None]) -> None:
    code, branch_id, run = _load(source, balances=True)
    # Qoldiq 1000 → 500, oqim −55: «Разница» −445 (1C talabnomalari ↔ bank qoldig'i) — nuqson emas.
    assert branch_id not in _identity_branches(run, rebuild(run), source)
    statement_branches([code])
    assert branch_id in _identity_branches(run, rebuild(run), source)


def test_staging_sink_records_extract_errors(source: str) -> None:
    run = open_run(source)
    with etl_transaction() as conn:
        sink = DbStagingSink(conn, run, source)
        assert isinstance(sink, ReportingSink)
        sink.error(target="bank_file", code="bad_row", message="x" * 600, src_id="f.csv:3")
    with etl_transaction() as conn:
        row = conn.execute(text(
            "SELECT step, severity, target, code, length(message) AS n, src_id "
            "FROM core.etl_error WHERE run_id = :r"), {"r": run}).one()
    assert (row.step, row.severity, row.target, row.code, row.n, row.src_id) == (
        "extract", "error", "bank_file", "bad_row", 500, "f.csv:3")


def test_fx_rate_latest_view(source: str) -> None:
    run = open_run(source)
    stage(run, source, {"fx_rate": [{"currency": "XTQ", "date_id": 20260901, "rate": 10},
                                     {"currency": "XTQ", "date_id": 20260910, "rate": 11}]})
    merge_all(run, source)
    with new_session() as s:
        row = s.execute(text("SELECT date_id, rate FROM pub.fx_rate_latest "
                             "WHERE currency = 'XTQ'")).one()
    assert (row.date_id, float(row.rate)) == (20260910, 11.0)
