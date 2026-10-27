from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import apply_rls, new_session
from app.dwh import builds
from app.etl.db import etl_transaction
from tests.etl_helpers import merge_all, new_source, open_run, purge_source, stage
from tests.s1_helpers import rebuild
from tests.s3_helpers import ProdScenario, production_rows, production_scenario

TABLES = ("agg_generation_month", "agg_energy_sales_month")
COLS = ("days_in_period", "days_in_month", "stations", "capacity_mw", "capacity_hours",
        "generation", "generation_cmp", "own_needs", "plan", "plan_full")


@pytest.fixture
def sc() -> Iterator[ProdScenario]:
    source = new_source()
    yield production_scenario(source)
    purge_source(source)


def _rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    with etl_transaction() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def _gen(build_id: int, branch_id: int) -> dict[int, tuple[float | None, ...]]:
    rows = _rows(f"SELECT month_id, {', '.join(COLS)} FROM mart.agg_generation_month "
                 "WHERE build_id = :b AND branch_id = :br", b=build_id, br=branch_id)
    return {r["month_id"]: tuple(None if r[c] is None else float(r[c]) for c in COLS)
            for r in rows}


def test_generation_month_rows(sc: ProdScenario) -> None:
    got = _gen(sc.build_id, sc.branch_id)
    assert got[202608] == (31, 31, 1, 100.0, 74400.0, 1.8, 1.8, 0.04, 2.0, 2.0)
    assert got[202609] == (24, 30, 1, 100.0, 57600.0, 1.0, 1.0, 0.02, 1.2, 1.5)
    assert got[202509] == (30, 30, 1, 100.0, 72000.0, 1.2, 0.5, 0.02, 1.2, 1.2)
    assert got[202508] == (31, 31, 1, 100.0, 74400.0, 1.5, 1.5, 0.03, 0.0, 0.0)
    # Ishlab chiqarishsiz oy ham bor — КИУМ maxrajida soatlar hisobga olinadi.
    assert got[202607] == (31, 31, 1, 100.0, 74400.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    assert min(got) == 202501 and max(got) == 202609
    assert _gen(sc.build_id, sc.hq_id) == {}
    total = _gen(sc.build_id, 0)[202608]
    assert total[2] >= 1 and total[5] >= 1.8


def test_energy_sales_rows(sc: ProdScenario) -> None:
    rows = _rows("SELECT month_id, accrued, paid, volume FROM mart.agg_energy_sales_month "
                 "WHERE build_id = :b AND branch_id = :br ORDER BY month_id",
                 b=sc.build_id, br=sc.branch_id)
    assert [(r["month_id"], float(r["accrued"]), float(r["paid"]), float(r["volume"]))
            for r in rows] == [(202608, 1200.0, 900.0, 1.0), (202609, 500.0, 450.0, 1.0)]


def test_capacity_version_applies_per_month(sc: ProdScenario) -> None:
    run = open_run(sc.source)
    stage(run, sc.source, {"dim_branch": [{**production_rows(sc.tag)["dim_branch"][0],
                                           "capacity_mw": 120}]})
    merge_all(run, sc.source, as_of=date(2026, 9, 1))
    build_id = rebuild(run)
    got = _gen(build_id, sc.branch_id)
    assert (got[202608][3], got[202608][4]) == (100.0, 74400.0)
    assert (got[202609][3], got[202609][4]) == (120.0, 69120.0)


def test_rls_and_failed_build(sc: ProdScenario) -> None:
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
