from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.core.db import apply_rls, new_session
from app.sections.period import resolve_period
from app.sections.queries import investment
from app.sections.scope import BranchSel
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.s4_helpers import InvScenario, investment_scenario


@pytest.fixture(scope="module")
def sc() -> Iterator[InvScenario]:
    source = new_source()
    yield investment_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _objects(db: Session, sc: InvScenario, per: str) -> dict[int, investment.InvObject]:
    rows = investment.objects(db, BranchSel(sc.branch_id, True), resolve_period(per, TEST_AS_OF))
    return {o.object_id: o for o in rows}


def test_closed_month_objects(sc: InvScenario, db: Session) -> None:
    objs = _objects(db, sc, "m08")
    a, b = objs[sc.obj_a], objs[sc.obj_b]
    assert (a.plan_year, a.plan_to_date, a.fact_ytd, a.fact_period, a.prior) == (
        240.0, 120.0, 90.0, 40.0, 400.0)
    assert (a.execution, a.status, a.financial, a.physical, a.gap_pp) == (
        0.75, "lag", 0.49, 0.4, 9.0)
    assert (a.advance, a.advance_days) == (30.0, 91)
    assert (b.execution, b.status, b.financial, b.physical, b.gap_pp) == (
        0.9, "ok", 0.38, 0.05, 33.0)
    assert (b.advance, b.advance_days, b.source_name) == (20.0, 113, f"МФИ тест {sc.tag}")
    assert list(objs) == [sc.obj_a, sc.obj_b]  # yil rejasi bo'yicha kamayish


def test_totals(sc: InvScenario, db: Session) -> None:
    period = resolve_period("m08", TEST_AS_OF)
    t = investment.totals(list(_objects(db, sc, "m08").values()), period)
    assert (t.program, t.plan_to_date, t.fact_ytd, t.execution, t.fact_period) == (
        440.0, 220.0, 180.0, 0.818182, 130.0)
    assert (t.lagging, t.threatened, t.commissioning, t.total_cost, t.year) == (
        1, 0, 1, 1500.0, 2026)
    assert t.has_objects and len(t.objects) == 2


def test_open_month_prorates_schedule(sc: InvScenario, db: Session) -> None:
    objs = _objects(db, sc, "m09")
    a, b = objs[sc.obj_a], objs[sc.obj_b]
    assert (a.plan_to_date, a.fact_ytd, a.execution, a.status) == (168.0, 110.0, 0.654762, "risk")
    assert (a.physical, a.gap_pp, a.advance, a.advance_days) == (0.45, 6.0, 0.0, None)
    assert (b.plan_to_date, b.fact_ytd, b.execution, b.physical, b.gap_pp) == (
        180.0, 120.0, 0.666667, 0.05, 39.0)
    assert b.advance_days == 137
    t = investment.totals(list(objs.values()), resolve_period("m09", TEST_AS_OF))
    assert (t.plan_to_date, t.fact_ytd, t.execution, t.threatened) == (348.0, 230.0, 0.66092, 2)


def test_cumulative_sources_stages(sc: InvScenario, db: Session) -> None:
    sel = BranchSel(sc.branch_id, True)
    cum = {p.month_id: (p.plan, p.fact) for p in investment.cumulative(db, sel, 2026,
                                                                       TEST_AS_OF)}
    assert len(cum) == 12 and cum[202606] == (0.0, 0.0)
    assert (cum[202607], cum[202608], cum[202609]) == ((60.0, 50.0), (220.0, 180.0),
                                                       (380.0, 230.0))
    assert cum[202610] == (440.0, None) and cum[202612] == (440.0, None)
    src = investment.sources(list(_objects(db, sc, "m08").values()))
    assert [(s.name, s.plan_year, s.fact_ytd, s.share) for s in src] == [
        (f"Бюджет тест {sc.tag}", 240.0, 90.0, 0.375), (f"МФИ тест {sc.tag}", 200.0, 90.0, 0.45)]
    stages = investment.stages(db, sel)[sc.obj_a]
    assert [(s.stage_no, s.done, s.late) for s in stages] == [
        (1, True, False), (2, True, True), (3, False, True), (4, False, False)]
    assert stages[1].fact_date == date(2026, 7, 20) and stages[2].fact_date is None


def test_branch_without_objects(sc: InvScenario) -> None:
    with new_session() as s:
        apply_rls(s, None)
        rows = investment.objects(s, BranchSel(999_999, True), resolve_period("m08", TEST_AS_OF))
    t = investment.totals(rows, resolve_period("m08", TEST_AS_OF))
    assert rows == [] and not t.has_objects and t.execution is None and t.program == 0.0
    with new_session() as s:
        apply_rls(s, frozenset({sc.branch_id}))
        own = investment.objects(s, BranchSel(None, False), resolve_period("m08", TEST_AS_OF))
    assert {o.object_id for o in own} == {sc.obj_a, sc.obj_b}
