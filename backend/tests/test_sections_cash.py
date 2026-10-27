from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.core.db import apply_rls, new_session
from app.core.errors import ValidationFailed
from app.sections.fmt import fmt_money, fmt_pct
from app.sections.period import normalize_per, resolve_period
from app.sections.queries import cash
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


def test_format_helpers() -> None:
    assert fmt_money(1234.5) == "1,2 млрд"
    assert fmt_money(-12.345) == "−12,3 млн"
    assert fmt_money(2_500_000) == "2,5 трлн"
    assert fmt_money(1_000_000.5, 2) == "1,00 трлн"
    assert fmt_pct(0.8) == "80,0%"


def test_period_resolution() -> None:
    q3 = resolve_period("q3", TEST_AS_OF)
    assert q3.months == (202607, 202608, 202609) and q3.open_last
    assert q3.prev_months == (202507, 202508, 202509)
    assert abs(q3.month_equivalents - (2 + 24 / 30)) < 1e-9
    assert not resolve_period("m08", TEST_AS_OF).open_last
    with pytest.raises(ValidationFailed):
        resolve_period("m10", TEST_AS_OF)


def test_branch_sel_clauses() -> None:
    assert BranchSel(3, True).total() == ("branch_id = :sel_br", {"sel_br": 3})
    assert BranchSel(None, True).total("a.branch_id") == ("a.branch_id = 0", {})
    assert BranchSel(None, False).total() == ("branch_id <> 0", {})
    assert BranchSel(None, True).rows() == ("branch_id <> 0", {})
    assert BranchSel.of(None, frozenset({3})) == BranchSel(None, False)


def test_closed_month_totals(sc: Scenario, db: Session) -> None:
    t = cash.cash_totals(db, _sel(sc), resolve_period("m08", TEST_AS_OF))
    assert (t.opening, t.inflow, t.outflow, t.net, t.closing, t.diff) == \
        (1000.0, 100.0, 40.0, 60.0, 1060.0, 0.0)
    assert (t.inflow_prev, t.outflow_prev, t.opening_prev, t.closing_prev) == \
        (0.0, 0.0, None, 750.0)


def test_yoy_unclosed_month_uses_same_days(sc: Scenario, db: Session) -> None:
    t = cash.cash_totals(db, _sel(sc), resolve_period("m09", TEST_AS_OF))
    assert (t.opening, t.inflow, t.outflow, t.closing) == (1060.0, 30.0, 12.0, 1078.0)
    # 2025-09-28 dagi 5 kirmaydi (24-sanadan keyin); qoldiq — 24-sentabr 2025 holati.
    assert (t.inflow_prev, t.outflow_prev, t.opening_prev, t.closing_prev) == \
        (9.0, 7.0, 750.0, 755.0)
    assert t.diff_prev == 755.0 - (750.0 + 9.0 - 7.0)


def test_quarter_diff(sc: Scenario, db: Session) -> None:
    t = cash.cash_totals(db, _sel(sc), resolve_period("q3", TEST_AS_OF))
    assert (t.opening, t.inflow, t.outflow, t.closing) == (747.0, 130.0, 52.0, 1078.0)
    assert t.diff == 1078.0 - (747.0 + 78.0)


def test_items_banks_branches_detail(sc: Scenario, db: Session) -> None:
    period = resolve_period("m08", TEST_AS_OF)
    out = cash.items(db, _sel(sc), period, "out")
    assert [(i.item_id, i.amount) for i in out] == [(sc.item_out_id, 40.0)]
    assert [(i.item_id, i.amount) for i in cash.items(db, _sel(sc), period, "in")] == [
        (sc.item_in_id, 100.0)]
    split = cash.activity_split(out)
    assert [(a.activity, a.amount) for a in split] == [
        ("centralized", 0.0), ("operating", 40.0), ("investing", 0.0)]
    banks = {b.bank_name.split()[1]: b for b in cash.banks(db, _sel(sc), period)}
    assert (banks["А"].inflow, banks["А"].closing) == (100.0, 700.0)
    assert (banks["Б"].outflow, banks["Б"].closing) == (40.0, 360.0)
    rows = cash.by_branch(db, _sel(sc), period)
    assert [(r.branch_id, r.opening, r.inflow, r.outflow, r.closing, r.diff) for r in rows] == [
        (sc.branch_id, 1000.0, 100.0, 40.0, 1060.0, 0.0)]
    detail = cash.detail(db, _sel(sc), period)
    assert [(d.direction, d.item_id, d.amount) for d in detail] == [
        ("in", sc.item_in_id, 100.0), ("out", sc.item_out_id, 40.0)]


def test_monthly_series(sc: Scenario, db: Session) -> None:
    points = {p.month_id: p for p in cash.monthly(db, _sel(sc), TEST_AS_OF)}
    assert sorted(points) == [202600 + m for m in range(1, 10)]
    assert (points[202608].inflow, points[202608].outflow, points[202608].closing) == \
        (100.0, 40.0, 1060.0)
    assert (points[202609].inflow_prev, points[202609].outflow_prev) == (9.0, 7.0)


def test_item_branches_with_plan(sc: Scenario, db: Session) -> None:
    info, rows = cash.item_branches(db, _sel(sc), resolve_period("m08", TEST_AS_OF),
                                    sc.item_out_id)
    assert info.direction == "out"
    assert [(r.branch_id, r.fact, r.plan) for r in rows] == [(sc.branch_id, 40.0, 50.0)]


def test_multi_branch_scope_sums_only_own_rows(sc: Scenario) -> None:
    with new_session() as s:
        apply_rls(s, frozenset({sc.branch_id}))
        t = cash.cash_totals(s, BranchSel(None, all_scope=False),
                             resolve_period("m08", TEST_AS_OF))
    assert (t.inflow, t.outflow, t.opening, t.closing) == (100.0, 40.0, 1000.0, 1060.0)


def test_numeric_month_alias() -> None:
    # TZ xatcho'plari: per=05 == per=m05; kesh kaliti ham normallashgan bo'lishi kerak.
    assert resolve_period("05", TEST_AS_OF).code == "m05"
    assert normalize_per("05") == "m05" and normalize_per("ytd") == "ytd"
    with pytest.raises(ValidationFailed):
        resolve_period("13", TEST_AS_OF)
