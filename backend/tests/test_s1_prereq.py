from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from sqlalchemy import text

from app.dwh import builds
from app.dwh.aggregates import BuildParams, build_all
from app.dwh.reference import DEFAULT_SETTINGS, validate_setting
from app.dwh.targets import SCHEDULE_DOC_TYPE, TARGETS
from app.etl.db import etl_transaction
from tests.etl_helpers import (
    TEST_AS_OF,
    branch_row,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def _plan(src_id: str, day: int, branch: str, amount: float,
          doc_type: str = "payment_plan") -> dict[str, Any]:
    return {"doc_type": doc_type, "src_id": src_id, "date_id": day, "branch_code": branch,
            "item_code": "PKM54-O09", "amount": amount}


def _src_ids(source: str, table: str) -> set[str]:
    with etl_transaction() as conn:
        return set(conn.execute(
            text(f"SELECT src_id FROM dwh.{table} WHERE src_system = :s"), {"s": source}).scalars())


def test_s1_settings_defaults_and_validation() -> None:
    assert DEFAULT_SETTINGS["kazna.calendar_kinds"] == {
        "taxes": ["PKM54-O03"], "salary": ["PKM54-O05"], "loans": ["PKM54-O04"]}
    assert DEFAULT_SETTINGS["onec.orgs"] == []
    assert DEFAULT_SETTINGS["onec.income_enabled"] is False
    assert DEFAULT_SETTINGS["onec.page_limit"] == 100000
    assert validate_setting("etl.onec_full_cron", "0 2 * * *") == "0 2 * * *"
    assert validate_setting("etl.onec_incremental_cron", "0 10,13,16 * * *")
    orgs = [{"branch_code": "UGE-01", "org_uid": "a1b2-c3", "org_name": "АО «Узбекгидроэнерго»"}]
    assert validate_setting("onec.orgs", orgs) == orgs
    bad_values: list[tuple[str, Any]] = [
        ("onec.orgs", orgs + orgs),
        ("onec.orgs", [{"branch_code": "UGE-01", "org_uid": "a b", "org_name": "X"}]),
        ("onec.orgs", [{**orgs[0], "extra": 1}]),
        ("kazna.calendar_kinds", {"rent": ["X"]}),
        ("kazna.calendar_kinds", {"taxes": ["A"], "salary": ["A"]}),
        ("onec.income_enabled", "yes"),
        ("onec.page_limit", 10),
        ("etl.onec_full_cron", "every night"),
    ]
    for key, value in bad_values:
        with pytest.raises(ValueError):
            validate_setting(key, value)


def test_forward_flags() -> None:
    assert TARGETS["fact_payment_plan"].forward
    assert TARGETS["fact_loan_schedule"].forward
    assert not TARGETS["fact_cashflow"].forward
    assert not TARGETS["fact_target_funds"].forward


def test_forward_target_replaces_future_rows(source: str) -> None:
    branch = branch_row(new_tag())
    code = branch["code"]
    first = open_run(source)
    stage(first, source, {"dim_branch": [branch], "fact_payment_plan": [
        _plan("p-past", 20260801, code, 50),
        _plan("s-future", 20261005, code, 7, SCHEDULE_DOC_TYPE)]})
    merge_all(first, source, complete={"fact_payment_plan"})
    assert _src_ids(source, "fact_payment_plan") == {"p-past", "s-future"}
    second = open_run(source)
    stage(second, source, {"fact_payment_plan": [_plan("p-past", 20260801, code, 50)]})
    merge_all(second, source, complete={"fact_payment_plan"})
    assert _src_ids(source, "fact_payment_plan") == {"p-past"}


def test_non_forward_target_keeps_rows_after_window(source: str) -> None:
    tag = new_tag()
    branch = branch_row(tag)
    src = {"code": f"S-{tag}", "name": "Тестовый источник", "kind": "own"}
    fund = {"doc_type": "target_funds", "src_id": "tf-future", "date_id": 20261101,
            "branch_code": branch["code"], "source_code": src["code"], "allocated": 10, "used": 4}
    first = open_run(source)
    stage(first, source, {"dim_branch": [branch], "dim_source": [src], "fact_target_funds": [fund]})
    merge_all(first, source, complete={"fact_target_funds"})
    second = open_run(source)
    stage(second, source, {"fact_target_funds": []})
    merge_all(second, source, complete={"fact_target_funds"})
    assert _src_ids(source, "fact_target_funds") == {"tf-future"}


def test_payment_schedule_rows_excluded_from_plan_aggregate(source: str) -> None:
    branch = branch_row(new_tag())
    code = branch["code"]
    run = open_run(source)
    stage(run, source, {"dim_branch": [branch], "fact_payment_plan": [
        _plan("p1", 20260801, code, 50), _plan("s1", 20260815, code, 7, SCHEDULE_DOC_TYPE)]})
    merge_all(run, source)
    with etl_transaction() as conn:
        branch_id = conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                 {"c": code}).scalar_one()
        build_id = builds.create_build(conn, run)
        build_all(conn, build_id, BuildParams(as_of=TEST_AS_OF, date_from=date(2026, 1, 1)))
        plan = conn.execute(text(
            "SELECT plan_amount FROM mart.agg_payments_month WHERE build_id = :b "
            "AND branch_id = :br AND month_id = 202608"),
            {"b": build_id, "br": branch_id}).scalar_one()
        builds.mark_failed(conn, build_id)
    assert float(plan) == 50.0
