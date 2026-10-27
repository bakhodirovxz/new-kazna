from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import apply_rls, new_session
from app.dwh import builds
from app.etl.db import etl_transaction
from tests.etl_helpers import new_source, purge_source
from tests.s4_helpers import HrScenario, hr_scenario

COLS = ("headcount_plan", "headcount_fact", "hired", "fired", "overtime_hours")
LEAD, OPER = "Руководители", "Оперативный персонал"


@pytest.fixture
def sc() -> Iterator[HrScenario]:
    source = new_source()
    yield hr_scenario(source)
    purge_source(source)


def _rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    with etl_transaction() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def test_hr_month_snapshot_and_flows(sc: HrScenario) -> None:
    rows = _rows(f"SELECT month_id, category, {', '.join(COLS)} FROM mart.agg_hr_month "
                 "WHERE build_id = :b AND branch_id = :br", b=sc.build_id, br=sc.branch_id)
    got = {(r["month_id"], r["category"]): tuple(float(r[c]) for c in COLS) for r in rows}
    assert got == {
        (202607, LEAD): (10, 9, 0, 1, 15), (202607, OPER): (90, 82, 1, 1, 300),
        (202608, LEAD): (10, 9, 1, 0, 20), (202608, OPER): (90, 81, 2, 3, 400),
        (202609, LEAD): (10, 10, 1, 0, 10), (202609, OPER): (90, 80, 1, 2, 200),
    }
    total = _rows("SELECT sum(headcount_fact) AS f FROM mart.agg_hr_month WHERE build_id = :b "
                  "AND branch_id = 0 AND month_id = 202608", b=sc.build_id)
    assert float(total[0]["f"]) >= 90


def test_rls_and_failed_build(sc: HrScenario) -> None:
    with new_session() as s:
        apply_rls(s, frozenset({sc.branch_id}))
        seen = set(s.execute(text("SELECT DISTINCT branch_id FROM mart.agg_hr_month "
                                  "WHERE build_id = :b"), {"b": sc.build_id}).scalars())
    assert seen == {sc.branch_id}
    with etl_transaction() as conn:
        builds.mark_failed(conn, sc.build_id)
        count = conn.execute(text("SELECT count(*) FROM mart.agg_hr_month WHERE build_id = :b"),
                             {"b": sc.build_id}).scalar_one()
    assert count == 0
