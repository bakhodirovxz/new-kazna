from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import apply_rls, new_session
from app.dwh import builds
from app.etl.db import etl_transaction
from tests.etl_helpers import new_source, purge_source
from tests.s1_helpers import Scenario, treasury_scenario


@pytest.fixture
def scenario() -> Iterator[Scenario]:
    source = new_source()
    yield treasury_scenario(source)
    purge_source(source)


def _rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    with etl_transaction() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def test_cash_by_bank_flows_and_balances(scenario: Scenario) -> None:
    rows = _rows("SELECT month_id, bank_name, inflow, outflow, closing_balance, closing_cmp "
                 "FROM mart.agg_cash_bank_month WHERE build_id = :b AND branch_id = :br "
                 "ORDER BY month_id, bank_name", b=scenario.build_id, br=scenario.branch_id)
    by = {(r["month_id"], r["bank_name"].split()[1]): r for r in rows}
    aug_a, aug_b = by[(202608, "А")], by[(202608, "Б")]
    assert (float(aug_a["inflow"]), float(aug_a["outflow"]), float(aug_a["closing_balance"])) == \
        (100.0, 0.0, 700.0)
    assert (float(aug_b["inflow"]), float(aug_b["outflow"]), float(aug_b["closing_balance"])) == \
        (0.0, 40.0, 360.0)
    sep_ly_a, sep_ly_b = by[(202509, "А")], by[(202509, "Б")]
    # cmp_day = 24: A — 2025-09-20 dagi 455, B — 2025-08-31 dagi 300.
    assert (float(sep_ly_a["closing_balance"]), float(sep_ly_a["closing_cmp"])) == (459.0, 455.0)
    assert (float(sep_ly_b["closing_balance"]), float(sep_ly_b["closing_cmp"])) == (288.0, 300.0)
    total = _rows("SELECT sum(inflow) AS i FROM mart.agg_cash_bank_month WHERE build_id = :b "
                  "AND branch_id = 0 AND month_id = 202608", b=scenario.build_id)[0]
    assert float(total["i"]) >= 100


def test_payment_orders_by_status(scenario: Scenario) -> None:
    rows = _rows("SELECT month_id, status, doc_count, amount FROM mart.agg_payment_orders_month "
                 "WHERE build_id = :b AND branch_id = :br", b=scenario.build_id,
                 br=scenario.branch_id)
    got = {(r["month_id"], r["status"]): (r["doc_count"], float(r["amount"])) for r in rows}
    assert got == {
        (202608, "исполнено"): (2, 15.0), (202608, "отклонено"): (1, 2.0),
        (202609, "на согласовании"): (1, 8.0), (202609, "утверждено"): (1, 3.0),
    }


def test_target_funds_by_source(scenario: Scenario) -> None:
    rows = _rows("SELECT month_id, source_name, allocated, used FROM mart.agg_target_funds_month "
                 "WHERE build_id = :b AND branch_id = :br ORDER BY month_id",
                 b=scenario.build_id, br=scenario.branch_id)
    assert [(r["month_id"], float(r["allocated"]), float(r["used"])) for r in rows] == [
        (202608, 10.0, 4.0), (202609, 10.0, 6.0)]
    assert rows[0]["source_name"] == f"Тестовый источник {scenario.tag}"


def test_mart_rls_for_app_role(scenario: Scenario) -> None:
    for table in ("agg_cash_bank_month", "agg_payment_orders_month", "agg_target_funds_month"):
        with new_session() as s:
            apply_rls(s, frozenset({scenario.branch_id}))
            seen = set(s.execute(text(f"SELECT DISTINCT branch_id FROM mart.{table} "
                                      "WHERE build_id = :b"), {"b": scenario.build_id}).scalars())
        assert seen == {scenario.branch_id}, table


def test_failed_build_clears_new_tables(scenario: Scenario) -> None:
    with etl_transaction() as conn:
        builds.mark_failed(conn, scenario.build_id)
        for table in ("agg_cash_bank_month", "agg_payment_orders_month", "agg_target_funds_month"):
            count = conn.execute(text(f"SELECT count(*) FROM mart.{table} WHERE build_id = :b"),
                                 {"b": scenario.build_id}).scalar_one()
            assert count == 0, table
