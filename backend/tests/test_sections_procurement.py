from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.core.db import apply_rls, new_session
from app.sections.period import resolve_period
from app.sections.queries import procurement
from app.sections.scope import BranchSel
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.s4_helpers import ProcScenario, procurement_scenario


@pytest.fixture(scope="module")
def sc() -> Iterator[ProcScenario]:
    source = new_source()
    yield procurement_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _sel(sc: ProcScenario) -> BranchSel:
    return BranchSel(sc.branch_id, all_scope=True)


def _totals(db: Session, sc: ProcScenario, per: str) -> procurement.ProcFigures:
    return procurement.totals(db, _sel(sc), resolve_period(per, TEST_AS_OF))


def test_closed_month_totals(sc: ProcScenario, db: Session) -> None:
    t = _totals(db, sc, "m08")
    assert (t.contracted, t.contracts, t.start_contracted, t.savings) == (140.0, 2, 150.0, 10.0)
    assert t.savings_share == 0.066667 and t.direct_share == 0.357143
    assert (t.ytd, t.plan, t.plan_execution, t.avg_days) == (197.0, 1000.0, 0.197, 8.5)
    assert (t.in_work, t.in_work_start, t.overdue, t.overdue_start) == (1, 80.0, 1, 80.0)
    assert (t.cancelled, t.cancelled_start) == (1, 40.0) and t.has_data


def test_open_month_and_quarter(sc: ProcScenario, db: Session) -> None:
    t = _totals(db, sc, "m09")
    assert (t.contracted, t.savings, t.savings_share, t.direct_share) == (170.0, 30.0, 0.15, 0.0)
    assert (t.ytd, t.plan_execution, t.avg_days) == (367.0, 0.367, 60.0)
    assert (t.in_work, t.in_work_start, t.overdue, t.cancelled) == (2, 110.0, 1, 0)
    q = _totals(db, sc, "q3")
    assert (q.contracted, q.contracts, q.savings, q.direct_share, q.avg_days) == (
        310.0, 3, 40.0, 0.16129, 25.7)


def test_monthly_and_methods(sc: ProcScenario, db: Session) -> None:
    months = procurement.monthly(db, _sel(sc), TEST_AS_OF)
    assert [m.month_id for m in months] == list(range(202601, 202610))
    assert {m.month_id: m.contracted for m in months if m.contracted} == {
        202602: 57.0, 202608: 140.0, 202609: 170.0}
    rows = procurement.by_method(db, _sel(sc), resolve_period("m08", TEST_AS_OF))
    assert [(r.method, r.title, r.lots, r.start, r.contracted, r.savings, r.savings_share,
             r.avg_days, r.norm_days) for r in rows] == [
        ("eshop", "Электронный магазин", 1, 100.0, 90.0, 10.0, 0.1, 12.0, 15),
        ("direct", "Прямой договор", 1, 50.0, 50.0, 0.0, 0.0, 5.0, 12)]


def test_lot_registry_order_and_kinds(sc: ProcScenario, db: Session) -> None:
    rows = procurement.lots(db, _sel(sc), resolve_period("m08", TEST_AS_OF))
    assert [(r.lot_no, r.kind, r.overdue) for r in rows] == [
        ("L4", "work", True), ("L1", "done", False), ("L2", "done", False),
        ("L6", "cancelled", False)]
    first = rows[0]
    assert (first.days, first.norm_days, first.method_title, first.subject) == (
        85, 40, "Электронный конкурс", "Строительно-монтажные работы")
    assert first.branch_name == f"Тестовая ГЭС {sc.tag}" and first.date_id == 20260701
    assert [r.lot_no for r in procurement.lots(db, _sel(sc), resolve_period("m08", TEST_AS_OF),
                                               limit=2)] == ["L4", "L1"]
    assert [r.lot_no for r in procurement.cancelled(db, _sel(sc),
                                                    resolve_period("m08", TEST_AS_OF))] == ["L6"]


def test_suppliers_subjects_branches(sc: ProcScenario, db: Session) -> None:
    period = resolve_period("m08", TEST_AS_OF)
    assert [(s.name, s.amount, s.count) for s in procurement.suppliers(db, _sel(sc), period)] == [
        (f"ООО «Поставщик-1 {sc.tag}»", 90.0, 1), (f"ООО «Поставщик-2 {sc.tag}»", 50.0, 1)]
    assert [(s.name, s.amount) for s in procurement.subjects(db, _sel(sc), period)] == [
        ("Запасные части", 90.0), ("Ремонтные услуги", 50.0)]
    branches = procurement.by_branch(db, _sel(sc), period)
    assert [(b.branch_id, b.plan, b.ytd, b.execution, b.savings) for b in branches] == [
        (sc.branch_id, 1000.0, 197.0, 0.197, 10.0)]


def test_empty_selection_and_limited_scope(sc: ProcScenario) -> None:
    with new_session() as s:
        apply_rls(s, None)
        empty = procurement.totals(s, BranchSel(999_999, True), resolve_period("m08", TEST_AS_OF))
    assert not empty.has_data and empty.plan_execution is None and empty.avg_days is None
    assert empty.direct_share is None and empty.savings_share is None
    with new_session() as s:
        apply_rls(s, frozenset({sc.branch_id}))
        own = procurement.totals(s, BranchSel(None, all_scope=False),
                                 resolve_period("m08", TEST_AS_OF))
    assert (own.contracted, own.plan) == (140.0, 1000.0)
