from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import apply_rls, new_session
from app.dwh import builds
from app.etl.db import etl_transaction
from app.etl.zakupki.codes import DEFAULT_METHOD_NORMS
from tests.etl_helpers import new_source, purge_source
from tests.helpers import clear_setting, put_setting
from tests.s1_helpers import rebuild
from tests.s4_helpers import ProcScenario, procurement_scenario

TABLES = ("agg_procurement_lots", "agg_procurement_plan")


@pytest.fixture
def sc() -> Iterator[ProcScenario]:
    source = new_source()
    yield procurement_scenario(source)
    purge_source(source)


def _rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    with etl_transaction() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def _lots(build_id: int, branch_id: int) -> dict[str, dict[str, Any]]:
    rows = _rows("SELECT * FROM mart.agg_procurement_lots "
                 "WHERE build_id = :b AND branch_id = :br", b=build_id, br=branch_id)
    return {r["lot_no"]: r for r in rows}


def test_lot_registry(sc: ProcScenario) -> None:
    lots = _lots(sc.build_id, sc.branch_id)
    assert set(lots) == {f"L{i}" for i in range(1, 9)}  # reja qatorlari reyestrga kirmaydi
    l4, l5, l1 = lots["L4"], lots["L5"], lots["L1"]
    assert (l4["days"], l4["norm_days"], l4["overdue"], l4["month_id"]) == (85, 40, True, 202607)
    assert (l5["days"], l5["norm_days"], l5["overdue"]) == (14, 15, False)
    assert (l1["days"], l1["overdue"], float(l1["contract_price"])) == (12, False, 90.0)
    assert l1["supplier"] == f"ООО «Поставщик-1 {sc.tag}»" and l1["subject"] == "Запасные части"
    assert lots["L6"]["days"] is None and lots["L6"]["supplier"] is None
    assert lots["L8"]["month_id"] == 202508 and lots["L3"]["date_id"] == 20260905


def test_year_plan(sc: ProcScenario) -> None:
    rows = _rows("SELECT month_id, plan FROM mart.agg_procurement_plan WHERE build_id = :b "
                 "AND branch_id = :br ORDER BY month_id", b=sc.build_id, br=sc.branch_id)
    assert [(r["month_id"], float(r["plan"])) for r in rows] == [(202501, 500.0),
                                                                 (202601, 1000.0)]
    total = _rows("SELECT plan FROM mart.agg_procurement_plan WHERE build_id = :b "
                  "AND branch_id = 0 AND month_id = 202601", b=sc.build_id)
    assert float(total[0]["plan"]) >= 1000.0


def test_norm_change_applies_on_next_build(sc: ProcScenario) -> None:
    try:
        put_setting("zakupki.method_norms", {**DEFAULT_METHOD_NORMS, "contest": 80})
        build_id = rebuild(sc.run_id)
        l4 = _lots(build_id, sc.branch_id)["L4"]
        assert (l4["norm_days"], l4["overdue"]) == (80, False)  # 85 ≤ 80 + 10
        assert _lots(sc.build_id, sc.branch_id)["L4"]["overdue"] is True  # eski build o'zgarmaydi
    finally:
        clear_setting("zakupki.method_norms")


def test_rls_and_failed_build(sc: ProcScenario) -> None:
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
