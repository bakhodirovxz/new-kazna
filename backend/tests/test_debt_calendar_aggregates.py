from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import apply_rls, new_session
from app.etl.db import etl_transaction
from tests.etl_helpers import new_source, purge_source
from tests.helpers import clear_setting, put_setting
from tests.s1_helpers import Scenario, rebuild, treasury_scenario


@pytest.fixture
def scenario() -> Iterator[Scenario]:
    source = new_source()
    yield treasury_scenario(source)
    purge_source(source)


def _rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    with etl_transaction() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def test_debt_contracts_latest_snapshot_per_month(scenario: Scenario) -> None:
    rows = _rows("SELECT month_id, contract_number, kind, receivable, payable, overdue, "
                 "overdue_days, cp_name FROM mart.agg_debt_contracts WHERE build_id = :b "
                 "AND branch_id = :br ORDER BY month_id, contract_number",
                 b=scenario.build_id, br=scenario.branch_id)
    got = [(r["month_id"], r["kind"], float(r["receivable"]), float(r["payable"]),
            float(r["overdue"]), r["overdue_days"]) for r in rows]
    assert got == [
        (202608, "payable", 0.0, 100.0, 0.0, 0),
        (202608, "receivable", 50.0, 0.0, 10.0, 20),
        (202609, "payable", 0.0, 120.0, 60.0, 95),
    ]
    assert rows[0]["cp_name"] == f"ООО «Тест Поставщик {scenario.tag}»"


def test_debt_month_totals(scenario: Scenario) -> None:
    rows = _rows("SELECT month_id, receivable, payable, overdue_receivable, overdue_payable, "
                 "contracts FROM mart.agg_debt_month WHERE build_id = :b AND branch_id = :br "
                 "ORDER BY month_id", b=scenario.build_id, br=scenario.branch_id)
    assert [(r["month_id"], float(r["receivable"]), float(r["payable"]),
             float(r["overdue_receivable"]), float(r["overdue_payable"]), r["contracts"])
            for r in rows] == [(202608, 50.0, 100.0, 10.0, 0.0, 2),
                               (202609, 0.0, 120.0, 0.0, 60.0, 1)]


def test_calendar_14_days_by_kind(scenario: Scenario) -> None:
    rows = _rows("SELECT date_id, kind, amount, as_of_id, month_id FROM mart.agg_calendar_day "
                 "WHERE build_id = :b AND branch_id = :br", b=scenario.build_id,
                 br=scenario.branch_id)
    assert len(rows) == 14 * 4
    assert {r["as_of_id"] for r in rows} == {20260924}
    assert {r["month_id"] for r in rows} == {202609}
    assert min(r["date_id"] for r in rows) == 20260925
    assert max(r["date_id"] for r in rows) == 20261008
    nonzero = {(r["date_id"], r["kind"]): float(r["amount"]) for r in rows if r["amount"]}
    # s3 (2026-10-09) — 15-kun, gorizontdan tashqarida; kredit: (0,1 + 0,02) × 1000.
    assert nonzero == {(20260925, "contracts"): 6.0, (20261001, "contracts"): 4.0,
                       (20261002, "loans"): 120.0}


@pytest.fixture
def taxes_kind() -> Iterator[None]:
    put_setting("kazna.calendar_kinds", {"taxes": ["PKM54-O09"]})
    yield
    clear_setting("kazna.calendar_kinds")


def test_calendar_kind_follows_setting(scenario: Scenario, taxes_kind: None) -> None:
    build_id = rebuild(scenario.run_id)
    rows = _rows("SELECT date_id, kind, amount FROM mart.agg_calendar_day WHERE build_id = :b "
                 "AND branch_id = :br AND amount <> 0", b=build_id, br=scenario.branch_id)
    assert {(r["date_id"], r["kind"]) for r in rows} == {
        (20260925, "taxes"), (20261001, "taxes"), (20261002, "loans")}


def test_mart_rls_for_app_role(scenario: Scenario) -> None:
    for table in ("agg_debt_contracts", "agg_debt_month", "agg_calendar_day"):
        with new_session() as s:
            apply_rls(s, frozenset({scenario.branch_id}))
            seen = set(s.execute(text(f"SELECT DISTINCT branch_id FROM mart.{table} "
                                      "WHERE build_id = :b"), {"b": scenario.build_id}).scalars())
        assert seen == {scenario.branch_id}, table
