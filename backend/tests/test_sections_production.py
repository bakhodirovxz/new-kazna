from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.core.db import apply_rls, new_session
from app.sections.period import resolve_period
from app.sections.queries import production
from app.sections.scope import BranchSel
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.s3_helpers import ProdScenario, production_scenario


@pytest.fixture(scope="module")
def sc() -> Iterator[ProdScenario]:
    source = new_source()
    yield production_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _totals(db: Session, branch_id: int, per: str) -> production.GenFigures:
    return production.totals(db, BranchSel(branch_id, all_scope=True),
                             resolve_period(per, TEST_AS_OF))


def test_closed_month_totals(sc: ProdScenario, db: Session) -> None:
    t = _totals(db, sc.branch_id, "m08")
    assert (t.generation, t.generation_prev, t.plan, t.own_needs) == (1.8, 1.5, 2.0, 0.04)
    assert (t.capacity_mw, t.stations, t.capacity_hours) == (100.0, 1, 74400.0)
    assert t.supply == 1.76 and t.execution == 0.9
    assert t.kium == 0.024194 and t.own_share == 0.022222
    assert (t.accrued, t.paid, t.payment_level) == (1200.0, 900.0, 0.75)
    assert t.has_data


def test_open_month_prorates_plan_and_compares_same_days(sc: ProdScenario, db: Session) -> None:
    t = _totals(db, sc.branch_id, "m09")
    # Reja 1,5 × 24/30; o'tgan yil — faqat 1–24-sentabr 2025 (28-sentabrdagi 0,7 kirmaydi).
    assert (t.generation, t.generation_prev, t.plan) == (1.0, 0.5, 1.2)
    assert t.execution == 0.833333 and t.capacity_hours == 57600.0 and t.kium == 0.017361
    assert t.payment_level == 0.9


def test_quarter_sums_months(sc: ProdScenario, db: Session) -> None:
    t = _totals(db, sc.branch_id, "q3")
    assert (t.generation, t.generation_prev, t.plan) == (2.8, 2.0, 3.2)
    assert t.capacity_hours == 206400.0 and t.capacity_mw == 100.0


def test_station_rows_and_map(sc: ProdScenario, db: Session) -> None:
    sel = BranchSel(sc.branch_id, all_scope=True)
    rows = production.stations(db, sel, resolve_period("m08", TEST_AS_OF))
    assert [(r.branch_id, r.name, r.generation, r.plan, r.accrued) for r in rows] == [
        (sc.branch_id, f"Тестовая ГЭС {sc.tag}", 1.8, 2.0, 1200.0)]
    every = production.station_map(db, BranchSel(None, True), resolve_period("m08", TEST_AS_OF))
    assert every[sc.branch_id].execution == 0.9 and sc.hq_id not in every


def test_hq_has_no_stations(sc: ProdScenario, db: Session) -> None:
    assert production.has_stations(db, BranchSel(sc.branch_id, True)) is True
    assert production.has_stations(db, BranchSel(sc.hq_id, True)) is False
    assert production.has_stations(db, BranchSel(None, True)) is True
    t = _totals(db, sc.hq_id, "m08")
    assert not t.has_data and t.generation == 0.0 and t.capacity_mw is None
    assert (t.execution, t.kium, t.own_share, t.payment_level) == (None, None, None, None)


def test_monthly_series(sc: ProdScenario, db: Session) -> None:
    months = production.monthly(db, BranchSel(sc.branch_id, True), TEST_AS_OF)
    assert [m.month_id for m in months] == list(range(202601, 202610))
    by = {m.month_id: (m.generation, m.plan, m.generation_prev, m.accrued, m.paid)
          for m in months}
    assert by[202608] == (1.8, 2.0, 1.5, 1200.0, 900.0)
    assert by[202609] == (1.0, 1.2, 0.5, 500.0, 450.0)
    assert by[202601] == (0.0, 0.0, 0.0, 0.0, 0.0)


def test_limited_scope_sums_own_rows(sc: ProdScenario) -> None:
    with new_session() as s:
        apply_rls(s, frozenset({sc.branch_id}))
        t = production.totals(s, BranchSel(None, all_scope=False),
                              resolve_period("m08", TEST_AS_OF))
        assert production.has_stations(s, BranchSel(None, all_scope=False)) is True
    assert (t.generation, t.plan, t.accrued) == (1.8, 2.0, 1200.0)
