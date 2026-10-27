from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.core.db import apply_rls, new_session
from app.sections.period import resolve_period
from app.sections.queries import loans
from app.sections.scope import BranchSel
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.s2_helpers import LoanScenario, loan_scenario


@pytest.fixture(scope="module")
def sc() -> Iterator[LoanScenario]:
    source = new_source()
    yield loan_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _report(db: Session, sc: LoanScenario, per: str) -> loans.LoanReport:
    return loans.load_report(db, BranchSel(sc.branch_id, all_scope=True),
                             resolve_period(per, TEST_AS_OF))


def test_closed_month_report(sc: LoanScenario, db: Session) -> None:
    r = _report(db, sc, "m08")
    assert r.as_of == date(2026, 8, 31) and r.has_loans
    assert [(x.loan_id, x.outstanding) for x in r.loans] == [(sc.loan_a, 9000.0),
                                                              (sc.loan_b, 400.0)]
    assert r.portfolio == 9400.0 and r.missing_fx == []
    assert r.rate == pytest.approx(522 / 9400)  # (9000 × 5% + 400 × 18%) / 9400
    assert r.fx_share == pytest.approx(9000 / 9400) and r.fx_amount == 9000.0
    assert (r.service, r.paid) == (3208.0, 1630.0)
    assert r.paid_share == pytest.approx(1630 / 3208)
    nxt = r.next_payment
    assert nxt is not None
    assert (nxt.day, nxt.principal, nxt.interest, nxt.total) == (date(2026, 9, 15), 1000.0,
                                                                  460.0, 1460.0)
    assert nxt.creditor == f"Тест кредитор А {sc.tag}"
    assert r.peak is not None and (r.peak.year, r.peak.total) == (2028, 7350.0)
    assert [(y.year, y.principal, y.interest) for y in r.years[:3]] == [
        (2026, 2200.0, 1008.0), (2027, 1300.0, 418.0), (2028, 7000.0, 350.0)]
    assert len(r.years) == 10 and r.years[-1].year == 2035 and r.years[-1].total == 0.0
    assert [(p.day, p.total) for p in r.upcoming] == [
        (date(2026, 9, 15), 1460.0), (date(2026, 10, 10), 118.0), (date(2027, 3, 15), 1400.0),
        (date(2027, 10, 10), 318.0), (date(2028, 3, 15), 7350.0)]
    assert r.by_currency() == [("XTL", 9000.0), ("UZS", 400.0)]
    assert r.by_creditor() == [(f"Тест кредитор А {sc.tag}", 9000.0),
                               (f"Тест кредитор Б {sc.tag}", 400.0)]
    a, b = r.loans
    assert a.repaid_share == pytest.approx(0.1) and b.repaid_share == pytest.approx(0.2)
    assert not a.in_grace(r.as_of) and a.in_grace(date(2025, 12, 31))


def test_open_month_uses_current_rate(sc: LoanScenario, db: Session) -> None:
    r = _report(db, sc, "m09")
    assert r.as_of == TEST_AS_OF and r.portfolio == 9200.0  # 8 × 1100 + 400
    assert (r.service, r.paid) == (3504.0, 3386.0)
    assert r.next_payment is not None and r.next_payment.day == date(2026, 10, 10)


def test_quarter_uses_period_end(sc: LoanScenario, db: Session) -> None:
    assert _report(db, sc, "q3").portfolio == _report(db, sc, "m09").portfolio


def test_missing_fx_is_flagged_not_zero(sc: LoanScenario, db: Session) -> None:
    r = _report(db, sc, "m01")
    assert r.missing_fx == ["XTL"]
    assert r.portfolio == 500.0 and r.fx_share == 0.0
    a = next(x for x in r.loans if x.loan_id == sc.loan_a)
    assert a.outstanding is None and a.outstanding_cur == 10.0
    # Kursi yo'q kreditning to'lovlari yig'indilarga kirmaydi, ro'yxatda summasiz ko'rinadi.
    assert (r.upcoming[0].day, r.upcoming[0].total) == (date(2026, 3, 15), None)
    assert r.service == 248.0


def test_branch_without_loans(sc: LoanScenario, db: Session) -> None:
    r = loans.load_report(db, BranchSel(sc.empty_branch_id, True),
                          resolve_period("m08", TEST_AS_OF))
    assert not r.has_loans and r.loans == [] and r.payments == []
    assert (r.portfolio, r.rate, r.fx_share, r.next_payment, r.peak) == (None, None, None,
                                                                         None, None)
    assert r.paid_share is None and r.service == 0.0


def test_limited_scope_sees_only_own_loans(sc: LoanScenario) -> None:
    with new_session() as s:
        apply_rls(s, frozenset({sc.branch_id}))
        r = loans.load_report(s, BranchSel(None, all_scope=False),
                              resolve_period("m08", TEST_AS_OF))
    assert {x.branch_id for x in r.loans} == {sc.branch_id} and r.portfolio == 9400.0
