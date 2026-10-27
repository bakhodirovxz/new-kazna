from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from app.etl.synthetic import SyntheticConnector
from app.etl.synthetic.families import production, stock
from app.etl.synthetic.model import SynthModel
from app.etl.synthetic.reference import BRANCHES, HQ_ID
from app.etl.types import Window
from tests.etl_helpers import TEST_AS_OF


class CollectSink:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, Any]]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))


WINDOW = Window(date(2026, 8, 1), TEST_AS_OF)
CAPACITY = {b.code: b.capacity for b in BRANCHES}
HQ_CODE = BRANCHES[HQ_ID - 1].code


def _collect(family: Any) -> list[tuple[str, dict[str, Any]]]:
    sink = CollectSink()
    family.generate(SynthModel(7, TEST_AS_OF), WINDOW, sink)
    return sink.rows


def test_generation_within_capacity_hq_excluded_plan_monthly() -> None:
    rows = _collect(production)
    gen = [r for t, r in rows if t == "fact_generation"]
    daily = [r for r in gen if r["doc_type"] == production.DAILY_DOC]
    plans = [r for r in gen if r["doc_type"] == production.PLAN_DOC]
    assert len(production.stations()) == 15
    assert HQ_CODE not in {r["branch_code"] for r in gen}
    for r in daily:
        cap = CAPACITY[r["branch_code"]]
        assert cap is not None and r["generation"] * 1000 <= Decimal(cap * 24)
        assert Decimal(0) < r["own_needs"] < r["generation"] and r["plan"] is None
        assert WINDOW.contains_id(r["date_id"])
    assert len(daily) == 15 * (31 + 24)
    assert sorted({r["date_id"] for r in plans}) == [20260801, 20260901]
    assert all(r["generation"] == 0 and r["plan"] > 0 for r in plans)


def test_sales_split_between_buyers_and_dated_at_period_end() -> None:
    sales = [r for t, r in _collect(production) if t == "fact_energy_sales"]
    assert {r["cp_code"] for r in sales} == {"CP-013", "CP-014"}
    assert {r["date_id"] for r in sales} == {20260831, 20260924}
    assert len(sales) == 15 * 2 * 2
    for r in sales:
        assert r["accrued"] > 0 and r["paid"] <= r["accrued"] * Decimal("1.031")
        assert r["volume"] > 0


def test_stock_snapshots_and_moves() -> None:
    rows = _collect(stock)
    snaps = [r for t, r in rows if t == "fact_stock"]
    moves = [r for t, r in rows if t == "fact_stock_move"]
    assert {r["date_id"] for r in snaps} == {20260831, 20260924}
    per_branch = {b.code: sum(1 for r in snaps if r["branch_code"] == b.code and
                              r["date_id"] == 20260831) for b in BRANCHES}
    assert per_branch[HQ_CODE] == 6 and all(v == 10 for k, v in per_branch.items() if k != HQ_CODE)
    for r in snaps:
        assert r["src_id"].endswith(str(r["date_id"] // 100))  # oy src_id ichida
        assert r["last_move_date_id"] < r["date_id"] and r["min_qty"] is not None
        assert r["value"] >= 0 and r["warehouse"]
    assert {r["direction"] for r in moves} == {"in", "out"}
    assert all(WINDOW.contains_id(r["date_id"]) and r["value"] > 0 for r in moves)
    assert {r["date_id"] for r in moves} == {20260815, 20260915}


def test_families_are_deterministic() -> None:
    assert _collect(production) == _collect(production)
    assert _collect(stock) == _collect(stock)


def test_extract_reports_s3_targets() -> None:
    sink = CollectSink()
    stats = SyntheticConnector(seed=7, as_of=TEST_AS_OF).extract(WINDOW, sink)
    for target in ("fact_generation", "fact_energy_sales", "fact_stock", "fact_stock_move"):
        assert stats.by_target[target] == sum(1 for t, _ in sink.rows if t == target), target
