from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.core.db import apply_rls, new_session
from app.sections.period import resolve_period
from app.sections.queries import stock
from app.sections.scope import BranchSel
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.s3_helpers import StockScenario, stock_scenario


@pytest.fixture(scope="module")
def sc() -> Iterator[StockScenario]:
    source = new_source()
    yield stock_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _sel(sc: StockScenario) -> BranchSel:
    return BranchSel(sc.branch_id, all_scope=True)


def test_closed_month_totals(sc: StockScenario, db: Session) -> None:
    t = stock.totals(db, _sel(sc), resolve_period("m08", TEST_AS_OF))
    assert t.as_of == date(2026, 8, 31) and t.days == 31
    assert (t.value, t.positions, t.below_min, t.min_known) == (120.0, 3, 1, 2)
    assert (t.idle_value, t.age_known_value, t.inflow, t.outflow) == (80.0, 120.0, 100.0, 140.0)
    assert t.turnover_days == 26.6 and t.idle_share == 0.666667
    assert t.has_data and t.has_minimum and t.has_age


def test_open_month_and_quarter(sc: StockScenario, db: Session) -> None:
    t = stock.totals(db, _sel(sc), resolve_period("m09", TEST_AS_OF))
    assert t.as_of == TEST_AS_OF and (t.value, t.below_min, t.idle_value) == (127.2, 0, 19.2)
    assert (t.inflow, t.outflow, t.days) == (16.0, 8.8, 24)
    assert t.turnover_days == 346.9 and t.idle_share == 0.150943
    q = stock.totals(db, _sel(sc), resolve_period("q3", TEST_AS_OF))
    # Qiymat — davr oxiridagi snapshot; oborot — 3 oy; kunlar 1.07–24.09 = 86.
    assert (q.value, q.inflow, q.outflow, q.days) == (127.2, 116.0, 148.8, 86)
    assert q.turnover_days == 73.5


def test_categories_ages_and_branches(sc: StockScenario, db: Session) -> None:
    assert [(c.name, c.value) for c in stock.categories(db, _sel(sc), 202608)] == [
        ("Запасные части", 100.0), ("Масла и ГСМ", 20.0)]
    assert [(a.key, a.value) for a in stock.ages(db, _sel(sc), 202608)] == [
        ("le90", 40.0), ("d91_180", 0.0), ("d181_365", 20.0), ("gt365", 60.0), ("unknown", 0.0)]
    assert [(a.key, a.value) for a in stock.ages(db, _sel(sc), 202609)][-1] == ("unknown", 60.0)
    rows = stock.by_branch(db, _sel(sc), resolve_period("m08", TEST_AS_OF))
    assert [(r.branch_id, r.value, r.positions, r.below_min, r.idle_value) for r in rows] == [
        (sc.branch_id, 120.0, 3, 1, 80.0)]


def test_below_and_idle_positions(sc: StockScenario, db: Session) -> None:
    below = stock.positions(db, _sel(sc), 202608, "below")
    assert [(p.nom_code, p.warehouse, p.qty, p.min_qty, p.coverage) for p in below] == [
        (f"N1-{sc.tag}", "Склад А", 4.0, 10.0, 0.4)]
    assert below[0].branch_name == f"Тестовая ГЭС {sc.tag}" and below[0].unit == "шт"
    idle = stock.positions(db, _sel(sc), 202608, "idle")
    assert [(p.nom_code, p.value, p.age_days) for p in idle] == [
        (f"N3-{sc.tag}", 60.0, 456), (f"N2-{sc.tag}", 20.0, 233)]
    assert [p.nom_code for p in stock.positions(db, _sel(sc), 202609, "idle")] == [
        f"N2-{sc.tag}"]


def test_flows_series(sc: StockScenario, db: Session) -> None:
    months = stock.flows(db, _sel(sc), TEST_AS_OF)
    assert [m.month_id for m in months] == list(range(202601, 202610))
    by = {m.month_id: (m.inflow, m.outflow) for m in months}
    assert by[202608] == (100.0, 140.0) and by[202609] == (16.0, 8.8) and by[202601] == (0.0, 0.0)


def test_limited_scope_and_empty_branch(sc: StockScenario) -> None:
    with new_session() as s:
        apply_rls(s, frozenset({sc.branch_id}))
        t = stock.totals(s, BranchSel(None, all_scope=False), resolve_period("m08", TEST_AS_OF))
    assert t.value == 120.0
    with new_session() as s:
        apply_rls(s, None)
        empty = stock.totals(s, BranchSel(999_999, True), resolve_period("m08", TEST_AS_OF))
    assert not empty.has_data and empty.turnover_days is None and empty.idle_share is None
    assert empty.as_of == date(2026, 8, 31)
