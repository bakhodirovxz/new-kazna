from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import apply_rls, new_session
from app.dwh import builds
from app.etl.db import etl_transaction
from tests.etl_helpers import new_source, purge_source
from tests.s3_helpers import StockScenario, stock_scenario

TABLES = ("agg_stock_month", "agg_stock_positions")
COLS = ("positions", "value", "below_min", "min_known", "idle_value", "age_le90", "age_91_180",
        "age_181_365", "age_gt365", "age_unknown", "inflow", "outflow")
SPARE = "Запасные части"
OIL = "Масла и ГСМ"


@pytest.fixture
def sc() -> Iterator[StockScenario]:
    source = new_source()
    yield stock_scenario(source)
    purge_source(source)


def _rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    with etl_transaction() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def test_stock_month_by_category(sc: StockScenario) -> None:
    rows = _rows(f"SELECT month_id, category, snap_date_id, {', '.join(COLS)} "
                 "FROM mart.agg_stock_month WHERE build_id = :b AND branch_id = :br",
                 b=sc.build_id, br=sc.branch_id)
    got = {(r["month_id"], r["category"]): tuple(float(r[c]) for c in COLS) for r in rows}
    assert got == {
        (202608, SPARE): (2, 100, 1, 1, 60, 40, 0, 0, 60, 0, 100, 140),
        (202608, OIL): (1, 20, 0, 1, 20, 0, 0, 20, 0, 0, 0, 0),
        (202609, SPARE): (2, 108, 0, 1, 0, 48, 0, 0, 0, 60, 16, 8),
        (202609, OIL): (1, 19.2, 0, 1, 19.2, 0, 0, 19.2, 0, 0, 0, 0.8),
    }
    snaps = {(r["month_id"], r["category"]): r["snap_date_id"] for r in rows}
    assert snaps[(202608, SPARE)] == 20260831 and snaps[(202609, OIL)] == 20260924


def test_flagged_positions(sc: StockScenario) -> None:
    rows = _rows("SELECT month_id, nom_id, warehouse, qty, min_qty, value, age_days, below_min, "
                 "idle, unit FROM mart.agg_stock_positions WHERE build_id = :b AND branch_id = :br "
                 "ORDER BY month_id, nom_id", b=sc.build_id, br=sc.branch_id)
    n1, n2, n3 = sc.noms["N1"], sc.noms["N2"], sc.noms["N3"]
    got = [(r["month_id"], r["nom_id"], r["warehouse"], float(r["qty"]), r["age_days"],
            r["below_min"], r["idle"]) for r in rows]
    assert got == sorted([
        (202608, n1, "Склад А", 4.0, 11, True, False),
        (202608, n2, "Склад А", 500.0, 233, False, True),
        (202608, n3, "Склад Б", 2.0, 456, False, True),
        (202609, n2, "Склад А", 480.0, 257, False, True),
    ], key=lambda x: (x[0], x[1]))
    units = {r["nom_id"]: r["unit"] for r in rows}
    assert (units[n1], units[n2]) == ("шт", "л")


def test_branch_zero_totals_include_branch(sc: StockScenario) -> None:
    rows = _rows("SELECT sum(value) AS v, sum(below_min) AS b FROM mart.agg_stock_month "
                 "WHERE build_id = :b AND branch_id = 0 AND month_id = 202608",
                 b=sc.build_id)
    assert float(rows[0]["v"]) >= 120 and int(rows[0]["b"]) >= 1


def test_rls_and_failed_build(sc: StockScenario) -> None:
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
