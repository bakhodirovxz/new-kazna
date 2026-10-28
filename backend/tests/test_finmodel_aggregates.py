from collections.abc import Iterator
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import apply_rls, new_session
from app.dwh import builds
from app.etl.connectors import KNOWN_SOURCES, make_connector
from app.etl.db import etl_transaction
from app.etl.notify import LogNotifier
from app.etl.rebuild import RebuildConnector
from app.etl.runner import Runner
from app.etl.types import Mode
from app.finmodel.inputs import gather_inputs, load_assumptions
from app.finmodel.model import run_model
from tests.etl_helpers import FULL_WINDOW, TEST_AS_OF, new_source, purge_source
from tests.s1_helpers import rebuild
from tests.s5_helpers import FinScenario, fin_value, finmodel_scenario, put_fin

COLS = ("revenue", "opex", "tax", "ebitda", "capex", "debt_service", "net_flow", "balance")


def _q(value: Decimal, places: str) -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


@pytest.fixture
def sc() -> Iterator[FinScenario]:
    source = new_source()
    yield finmodel_scenario(source)
    purge_source(source)


def _rows(build_id: int) -> dict[tuple[str, int], dict[str, Any]]:
    with etl_transaction() as conn:
        rows = conn.execute(text(
            "SELECT * FROM mart.agg_finmodel_year WHERE build_id = :b"), {"b": build_id}
        ).mappings().all()
    return {(r["scenario"], int(r["year"])): dict(r) for r in rows}


def test_build_stores_four_scenarios_by_seven_years(sc: FinScenario) -> None:
    rows = _rows(sc.build_id)
    assert len(rows) == 28
    assert {s for s, _ in rows} == {"base", "water", "tariff", "fx"}
    assert {y for _, y in rows} == set(range(2026, 2033))
    first = rows[("base", 2026)]
    assert (first["branch_id"], first["month_id"], first["as_of_id"]) == (0, 202609, 20260924)
    assert first["covenant"] == Decimal("1.2") and "XFN" in first["missing_fx"]
    assert first["assumptions_at"] is not None and 1 <= first["opex_months"] <= 12


def test_rows_match_pure_model(sc: FinScenario) -> None:
    with etl_transaction() as conn:
        inputs, _ = gather_inputs(conn, TEST_AS_OF)
        assumptions = load_assumptions(conn)
    stored = _rows(sc.build_id)
    for scenario, sa in assumptions.scenarios.items():
        for row in run_model(inputs, sa, covenant=assumptions.covenant):
            got = stored[(scenario, row.year)]
            for col in COLS:
                expected = _q(getattr(row, col), "0.01")
                assert got[col] == expected, (scenario, row.year, col)
            assert got["generation"] == _q(row.generation, "0.001")
            assert got["covenant_breach"] is row.covenant_breach
            if row.dscr is None:
                assert got["dscr"] is None
            else:
                assert got["dscr"] == _q(row.dscr, "0.0001")
    water, base = stored[("water", 2028)], stored[("base", 2028)]
    assert abs(water["generation"] - base["generation"] * Decimal("0.85")) <= Decimal("0.001")


def test_rls_only_scope_all(sc: FinScenario) -> None:
    with new_session() as s:
        apply_rls(s, frozenset({1, 3}))
        scoped = s.execute(text("SELECT count(*) FROM mart.agg_finmodel_year "
                                "WHERE build_id = :b"), {"b": sc.build_id}).scalar_one()
    with new_session() as s:
        apply_rls(s, None)
        full = s.execute(text("SELECT count(*) FROM mart.agg_finmodel_year "
                              "WHERE build_id = :b"), {"b": sc.build_id}).scalar_one()
    assert (scoped, full) == (0, 28)


def test_failed_build_removes_rows(sc: FinScenario) -> None:
    with etl_transaction() as conn:
        builds.mark_failed(conn, sc.build_id)
    assert _rows(sc.build_id) == {}


def test_assumption_change_applies_on_next_build(sc: FinScenario) -> None:
    before = _rows(sc.build_id)[("tariff", 2027)]["revenue"]
    original = fin_value("tariff", 2027, "tariff_growth")
    put_fin("tariff", 2027, "tariff_growth", Decimal("0.2"))
    try:
        after = _rows(rebuild(sc.run_id))[("tariff", 2027)]["revenue"]
    finally:
        put_fin("tariff", 2027, "tariff_growth", original)
    assert after > before
    assert _rows(sc.build_id)[("tariff", 2027)]["revenue"] == before  # eski build o'zgarmaydi


def test_rebuild_connector_extracts_nothing() -> None:
    connector = make_connector("rebuild")
    assert isinstance(connector, RebuildConnector) and "rebuild" in KNOWN_SOURCES
    assert connector.healthcheck().ok and connector.watermark().value is None
    assert connector.control_totals(FULL_WINDOW) is None
    stats = connector.extract(FULL_WINDOW, _NoSink())
    assert (stats.rows, dict(stats.by_target)) == (0, {})


class _NoSink:
    def add(self, target: str, row: Any) -> None:
        raise AssertionError("rebuild hech narsa yozmasligi kerak")


def test_rebuild_source_publishes_new_model(published_synthetic: Any) -> None:
    original = fin_value("base", 2030, "kium")
    put_fin("base", 2030, "kium", Decimal("0.45"))
    try:
        result = Runner(make_connector("rebuild"), mode=Mode.FULL, notifier=LogNotifier(),
                        today=TEST_AS_OF).run()
    finally:
        put_fin("base", 2030, "kium", original)
    assert result.status == "success", result.error
    with new_session() as s:
        apply_rls(s, None)
        active = s.execute(text("SELECT active_build_id FROM core.data_version WHERE id = 1")
                           ).scalar_one()
        count = s.execute(text("SELECT count(*) FROM pub.agg_finmodel_year")).scalar_one()
    with etl_transaction() as conn:
        run = conn.execute(text("SELECT source, rows_in FROM core.etl_run WHERE id = :r"),
                           {"r": result.run_id}).one()
    assert active == result.build_id and count == 28
    assert (run.source, run.rows_in) == ("rebuild", 0)
