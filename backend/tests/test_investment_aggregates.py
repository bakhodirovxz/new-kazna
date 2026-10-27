from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import apply_rls, new_session
from app.dwh import builds
from app.etl.db import etl_transaction
from tests.etl_helpers import new_source, purge_source
from tests.s4_helpers import InvScenario, investment_scenario

TABLES = ("agg_investment_month", "agg_object_stages")
COLS = ("plan", "fact", "opening", "physical_pct", "advance", "advance_date_id")


@pytest.fixture
def sc() -> Iterator[InvScenario]:
    source = new_source()
    yield investment_scenario(source)
    purge_source(source)


def _rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    with etl_transaction() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def _months(sc: InvScenario, obj: int) -> dict[int, tuple[Any, ...]]:
    rows = _rows(f"SELECT month_id, {', '.join(COLS)} FROM mart.agg_investment_month "
                 "WHERE build_id = :b AND object_id = :o", b=sc.build_id, o=obj)
    return {r["month_id"]: tuple(None if r[c] is None else
                                 (int(r[c]) if c == "advance_date_id" else float(r[c]))
                                 for c in COLS) for r in rows}


def test_object_months_with_forward_fill(sc: InvScenario) -> None:
    a = _months(sc, sc.obj_a)
    assert min(a) == 202501 and max(a) == 202612 and len(a) == 24
    assert a[202501] == (0.0, 0.0, 300.0, None, 0.0, None)
    assert a[202510] == (100.0, 100.0, 0.0, None, 0.0, None)
    assert a[202606] == (0.0, 0.0, 0.0, None, 0.0, None)
    assert a[202607] == (60.0, 50.0, 0.0, 0.4, 30.0, 20260601)
    assert a[202608] == (60.0, 40.0, 0.0, 0.4, 30.0, 20260601)  # КС-2 oldinga to'ldirildi
    assert a[202609] == (60.0, 20.0, 0.0, 0.45, 0.0, None)  # avans yopildi
    assert a[202610] == (60.0, 0.0, 0.0, None, None, None)  # as_of dan keyin — NULL
    b = _months(sc, sc.obj_b)
    assert b[202609] == (100.0, 30.0, 0.0, 0.05, 20.0, 20260510)
    assert b[202607] == (0.0, 0.0, 0.0, None, 0.0, None)


def test_object_attributes_denormalized(sc: InvScenario) -> None:
    row = _rows("SELECT object_code, name, work_type, source_name, commissioning_year, "
                "total_cost FROM mart.agg_investment_month WHERE build_id = :b "
                "AND object_id = :o AND month_id = 202608", b=sc.build_id, o=sc.obj_b)[0]
    assert (row["object_code"], row["name"], row["work_type"], row["source_name"],
            row["commissioning_year"], float(row["total_cost"])) == (
        f"OB-{sc.tag}", f"Объект Б {sc.tag}", "reconstruction", f"МФИ тест {sc.tag}", 2027,
        500.0)


def test_stages_snapshot(sc: InvScenario) -> None:
    rows = _rows("SELECT month_id, stage_no, plan_date_id, fact_date_id, done, late "
                 "FROM mart.agg_object_stages WHERE build_id = :b AND object_id = :o "
                 "ORDER BY stage_no", b=sc.build_id, o=sc.obj_a)
    assert [(r["month_id"], r["stage_no"], r["done"], r["late"]) for r in rows] == [
        (202609, 1, True, False), (202609, 2, True, True), (202609, 3, False, True),
        (202609, 4, False, False)]


def test_rls_and_failed_build(sc: InvScenario) -> None:
    for table in TABLES:
        with new_session() as s:
            apply_rls(s, frozenset({sc.branch_id}))
            seen = set(s.execute(text(f"SELECT DISTINCT branch_id FROM mart.{table} "
                                      "WHERE build_id = :b"), {"b": sc.build_id}).scalars())
        assert seen == {sc.branch_id}, table
    with etl_transaction() as conn:
        builds.mark_failed(conn, sc.build_id)
        for table in TABLES:
            count = conn.execute(text(f"SELECT count(*) FROM mart.{table} WHERE build_id = :b"),
                                 {"b": sc.build_id}).scalar_one()
            assert count == 0, table
