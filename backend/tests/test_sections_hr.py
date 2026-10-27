from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.core.db import apply_rls, new_session
from app.sections.period import resolve_period
from app.sections.queries import hr
from app.sections.scope import BranchSel
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.s4_helpers import HrScenario, hr_scenario


@pytest.fixture(scope="module")
def sc() -> Iterator[HrScenario]:
    source = new_source()
    yield hr_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _totals(db: Session, sc: HrScenario, per: str) -> hr.HrFigures:
    return hr.totals(db, BranchSel(sc.branch_id, True), resolve_period(per, TEST_AS_OF),
                     [sc.salary_code])


def test_closed_month_totals(sc: HrScenario, db: Session) -> None:
    t = _totals(db, sc, "m08")
    assert (t.snap_month, t.plan, t.fact, t.vacancies, t.vacancy_share, t.fill) == (
        202608, 100.0, 90.0, 10.0, 0.1, 0.9)
    assert (t.payroll, t.outflow, t.payroll_share, t.avg_salary) == (180.0, 600.0, 0.3, 2.0)
    assert (t.hired, t.fired, t.turnover) == (3, 3, 0.033333)
    assert (t.overtime, t.overtime_per_employee) == (420.0, 4.666667) and t.has_data


def test_open_month_uses_month_equivalents(sc: HrScenario, db: Session) -> None:
    t = _totals(db, sc, "m09")
    assert (t.snap_month, t.fact, t.payroll, t.payroll_share, t.months) == (
        202609, 90.0, 150.0, 0.6, 0.8)
    assert (t.avg_salary, t.turnover, t.overtime_per_employee) == (2.083333, 0.022222, 2.333333)
    q = _totals(db, sc, "q3")
    assert (q.payroll, q.outflow, q.payroll_share, q.avg_salary) == (500.0, 1020.0, 0.490196,
                                                                      1.984127)
    assert (q.hired, q.fired, q.turnover, q.overtime, q.overtime_per_employee) == (
        6, 7, 0.077778, 945.0, 10.5)


def test_categories_branches_months(sc: HrScenario, db: Session) -> None:
    sel = BranchSel(sc.branch_id, True)
    period = resolve_period("m08", TEST_AS_OF)
    assert [(c.name, c.value) for c in hr.categories(db, sel, period)] == [
        ("Оперативный персонал", 81.0), ("Руководители", 9.0)]
    rows = hr.by_branch(db, sel, period, [sc.salary_code])
    assert [(r.branch_id, r.plan, r.fact, r.vacancies, r.payroll, r.avg_salary, r.turnover)
            for r in rows] == [(sc.branch_id, 100.0, 90.0, 10.0, 180.0, 2.0, 0.033333)]
    months = {m.month_id: m for m in hr.monthly(db, sel, TEST_AS_OF, [sc.salary_code])}
    assert list(months) == list(range(202601, 202610))
    assert (months[202607].payroll, months[202607].fact, months[202607].avg_salary) == (
        170.0, 91.0, 1.868132)
    assert (months[202609].avg_salary, months[202609].hired, months[202609].fired) == (
        2.083333, 2, 2)
    assert months[202601].avg_salary is None and months[202601].payroll == 0.0


def test_period_without_hr_data(sc: HrScenario, db: Session) -> None:
    t = _totals(db, sc, "m06")
    assert not t.has_data and t.snap_month is None
    assert (t.vacancies, t.avg_salary, t.turnover, t.overtime_per_employee) == (
        None, None, None, None)
    no_codes = hr.totals(db, BranchSel(sc.branch_id, True), resolve_period("m08", TEST_AS_OF), [])
    assert no_codes.payroll == 0.0 and no_codes.outflow == 600.0


def test_limited_scope(sc: HrScenario) -> None:
    with new_session() as s:
        apply_rls(s, frozenset({sc.branch_id}))
        t = hr.totals(s, BranchSel(None, all_scope=False), resolve_period("m08", TEST_AS_OF),
                      [sc.salary_code])
    assert (t.plan, t.fact, t.payroll) == (100.0, 90.0, 180.0)
