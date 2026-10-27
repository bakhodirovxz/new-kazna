from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.core.db import apply_rls, new_session
from app.sections.period import resolve_period
from app.sections.queries import calendar, debt, funds, payments
from app.sections.scope import BranchSel
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.s1_helpers import Scenario, treasury_scenario


@pytest.fixture(scope="module")
def sc() -> Iterator[Scenario]:
    source = new_source()
    yield treasury_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _sel(sc: Scenario) -> BranchSel:
    return BranchSel(sc.branch_id, all_scope=True)


def test_plan_fact(sc: Scenario, db: Session) -> None:
    rows = payments.plan_fact(db, _sel(sc), resolve_period("m08", TEST_AS_OF))
    assert [(r.item_id, r.plan, r.fact, r.execution, r.deviation) for r in rows] == [
        (sc.item_out_id, 50.0, 40.0, 0.8, 10.0)]
    sep = payments.plan_fact(db, _sel(sc), resolve_period("m09", TEST_AS_OF))
    assert (sep[0].plan, sep[0].fact) == (30.0, 12.0)  # jadval qatorlari (6+4+3) rejaga kirmaydi


def test_orders_and_requests(sc: Scenario, db: Session) -> None:
    statuses = payments.orders_by_status(db, _sel(sc), resolve_period("m08", TEST_AS_OF))
    assert [s.status for s in statuses] == list(payments.PO_STATUSES)
    got = {s.status: (s.count, s.amount) for s in statuses}
    assert got["исполнено"] == (2, 15.0) and got["отклонено"] == (1, 2.0)
    assert got["черновик"] == (0, 0.0)
    assert payments.requests_total(db, _sel(sc)) == (2, 11.0)
    assert [(r.branch_id, r.count, r.amount) for r in payments.requests_by_branch(db, _sel(sc))] \
        == [(sc.branch_id, 2, 11.0)]


def test_debt(sc: Scenario, db: Session) -> None:
    summary = debt.debt_summary(db, _sel(sc), 202609)
    assert summary is not None
    assert (summary.receivable, summary.payable, summary.overdue_payable, summary.contracts) == \
        (0.0, 120.0, 60.0, 1)
    assert debt.debt_summary(db, _sel(sc), 202607) is None
    aug = debt.contracts(db, _sel(sc), 202608)
    assert [(c.kind, c.amount, c.overdue_days) for c in aug] == [
        ("receivable", 50.0, 20), ("payable", 100.0, 0)]
    assert aug[1].end_date == date(2026, 12, 31)
    assert [c.overdue_days for c in debt.overdue_contracts(db, _sel(sc), 202609, 90)] == [95]
    assert debt.overdue_contracts(db, _sel(sc), 202609, 95) == []
    assert [(r.branch_id, r.payable, r.overdue_payable) for r in
            debt.debt_by_branch(db, _sel(sc), 202609)] == [(sc.branch_id, 120.0, 60.0)]


def test_funds(sc: Scenario, db: Session) -> None:
    period = resolve_period("q3", TEST_AS_OF)
    sources = funds.funds_by_source(db, _sel(sc), period)
    assert [(f.allocated, f.used, f.share) for f in sources] == [(20.0, 10.0, 0.5)]
    assert [(f.key, f.used) for f in funds.funds_by_branch(db, _sel(sc), period)] == [
        (sc.branch_id, 10.0)]


def test_calendar_and_balances(sc: Scenario, db: Session) -> None:
    block = calendar.calendar(db, _sel(sc))
    assert block.as_of == TEST_AS_OF and block.start == date(2026, 9, 25)
    assert len(block.days) == 14 and block.total == 130.0
    assert (block.days[0].contracts, block.days[7].loans) == (6.0, 120.0)
    assert block.balance == 1078.0
    assert block.coverage is not None and abs(block.coverage - 1078 / 130) < 1e-9
    balances = calendar.bank_balances(db, _sel(sc), 202608)
    assert [(b.bank_name.split()[1], b.balance) for b in balances] == [("А", 700.0), ("Б", 360.0)]
