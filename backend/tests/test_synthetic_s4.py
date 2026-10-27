from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from app.etl.synthetic import SyntheticConnector
from app.etl.synthetic.families import hr, investment, procurement
from app.etl.synthetic.model import SynthModel
from app.etl.synthetic.reference import (
    BRANCHES,
    HQ_ID,
    OBJECTS,
    POSITIONS,
    PROCUREMENT_SUBJECTS,
)
from app.etl.types import Window
from app.etl.zakupki import codes
from tests.etl_helpers import TEST_AS_OF


class CollectSink:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, Any]]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))


YEAR = Window(date(2026, 1, 1), TEST_AS_OF)
MODEL = SynthModel(7, TEST_AS_OF)


def _collect(family: Any, window: Window = YEAR) -> list[dict[str, Any]]:
    sink = CollectSink()
    family.generate(MODEL, window, sink)
    return [r for _, r in sink.rows]


def test_lot_rows_use_codes_and_consistent_amounts() -> None:
    rows = [r for r in _collect(procurement) if r["doc_type"] == procurement.LOT_DOC]
    assert rows and {r["status"] for r in rows} <= set(codes.STATUSES) - {codes.PLAN_STATUS}
    assert {r["method"] for r in rows} <= set(codes.METHODS)
    for r in rows:
        assert YEAR.contains_id(r["date_id"])
        assert r["nom_code"].startswith("PS-") and r["start_price"] > 0
        if r["status"] == codes.DONE:
            assert r["contract_price"] is not None and r["contract_price"] <= r["start_price"]
            assert r["cp_code"].startswith("CP-") and r["procedure_days"] >= 3
        else:
            assert r["contract_price"] is None and r["cp_code"] is None
            assert r["procedure_days"] is None


def test_in_work_lots_include_overdue_ones() -> None:
    rows = [r for r in _collect(procurement) if r["status"] in codes.IN_WORK]
    assert rows
    overdue = [r for r in rows
               if (TEST_AS_OF - date(r["date_id"] // 10000, r["date_id"] // 100 % 100,
                                     r["date_id"] % 100)).days
               > codes.DEFAULT_METHOD_NORMS[r["method"]] + codes.LATE_MARGIN_DAYS]
    assert overdue, "sintetik ma'lumotda kechikkan lotlar bo'lishi kerak (qoida demosi)"


def test_year_plan_rows() -> None:
    plans = [r for r in _collect(procurement) if r["doc_type"] == codes.PLAN_DOC]
    assert len(plans) == len(BRANCHES)
    assert {r["date_id"] for r in plans} == {20260101}
    for r in plans:
        assert (r["status"], r["method"], r["contract_price"]) == (codes.PLAN_STATUS,
                                                                   codes.PLAN_METHOD, None)
    branch = BRANCHES[1]
    expected = procurement.year_plan(MODEL, branch, 2026)
    got = next(r for r in plans if r["branch_code"] == branch.code)["start_price"]
    assert got == Decimal(f"{expected:.2f}")
    # Reja butun yil lotlaridan (kelajak oylar ham) — as_of'ga bog'liq emas.
    assert expected == procurement.year_plan(SynthModel(7, date(2026, 12, 31)), branch, 2026)


def test_lot_state_rules() -> None:
    branch = BRANCHES[1]
    lots = [lot for m in MODEL.months() for lot in procurement.lots_for(MODEL, branch, m)]
    for lot in lots:
        state = procurement.lot_state(lot, TEST_AS_OF)
        if lot.announce > TEST_AS_OF:
            assert state is None
            continue
        assert state is not None
        status, day = state
        assert day <= TEST_AS_OF
        if status == codes.DONE:
            assert day == lot.contract_day
        else:
            assert day == lot.announce


def test_subject_dims_and_determinism() -> None:
    sink = CollectSink()
    SyntheticConnector(seed=7, as_of=TEST_AS_OF).extract(YEAR, sink)
    subjects = {r["code"]: r for t, r in sink.rows
                if t == "dim_nomenclature" and r["code"].startswith("PS-")}
    assert [subjects[f"PS-{i:02d}"]["category"] for i in range(1, 8)] == list(
        PROCUREMENT_SUBJECTS)
    assert _collect(procurement) == _collect(procurement)


FULL = Window(date(2024, 1, 1), TEST_AS_OF)


def _by_target(family: Any, window: Window) -> dict[str, list[dict[str, Any]]]:
    sink = CollectSink()
    family.generate(MODEL, window, sink)
    out: dict[str, list[dict[str, Any]]] = {}
    for target, row in sink.rows:
        out.setdefault(target, []).append(row)
    return out


def test_investment_rows_cover_year_and_stay_within_cost() -> None:
    rows = _by_target(investment, FULL)
    inv = rows["fact_investment"]
    months = [r for r in inv if r["doc_type"] == investment.MONTH_DOC]
    assert {r["date_id"] // 100 for r in months} == {
        y * 100 + m for y in (2025, 2026) for m in range(1, 13)}
    assert all(r["date_id"] % 100 == 1 for r in months)  # oyning 1-kuni
    future = [r for r in months if r["date_id"] > 20260924]
    assert future and all(r["fact"] == 0 and r["physical_pct"] is None for r in future)
    openings = [r for r in inv if r["doc_type"] == investment.OPEN_DOC]
    assert len(openings) == len(OBJECTS) and {r["date_id"] for r in openings} == {20240101}
    for n, obj in enumerate(OBJECTS, start=1):
        total = Decimal(obj[4] * 1000)
        spent = sum(r["fact"] for r in inv if r["object_code"] == f"OBJ-{n:02d}")
        assert Decimal(0) < spent < total, n
        plan26 = sum(r["plan"] for r in months if r["object_code"] == f"OBJ-{n:02d}"
                     and r["date_id"] // 10000 == 2026)
        assert abs(plan26 - Decimal(obj[5] * 1000)) < Decimal("0.1"), n
        assert all(r["branch_code"] == BRANCHES[obj[1]].code for r in inv
                   if r["object_code"] == f"OBJ-{n:02d}")
    phys = [r["physical_pct"] for r in months if r["physical_pct"] is not None]
    assert phys and all(Decimal(0) < p <= Decimal("0.98") for p in phys)
    adv = [r for r in months if r["advance"] > 0]
    assert adv and all(r["advance_date_id"] is not None for r in adv)


def test_investment_forward_emission_and_stages() -> None:
    inc = _by_target(investment, Window(date(2026, 8, 1), TEST_AS_OF))
    dates = {r["date_id"] for r in inc["fact_investment"]}
    assert min(dates) == 20260801 and max(dates) == 20261201
    stages = _by_target(investment, FULL)["fact_object_stage"]
    assert len(stages) == len(OBJECTS) * len(investment.STAGES)
    for r in stages:
        assert 1 <= r["stage_no"] <= 7 and r["stage_name"] in investment.STAGES
        if r["fact_date_id"] is not None:
            assert r["fact_date_id"] <= 20260924


def test_hr_rows() -> None:
    rows = _by_target(hr, Window(date(2026, 8, 1), TEST_AS_OF))["fact_hr"]
    assert {r["date_id"] for r in rows} == {20260831, 20260924}
    assert len(rows) == len(BRANCHES) * len(POSITIONS) * 2
    hq = [r for r in rows if r["branch_code"] == BRANCHES[HQ_ID - 1].code
          and r["date_id"] == 20260831]
    assert sum(r["headcount_plan"] for r in hq) == 182
    for r in rows:
        assert Decimal(0) <= r["headcount_fact"] <= r["headcount_plan"] + 1
        assert r["hired"] >= 0 and r["fired"] >= 0 and r["overtime_hours"] >= 0
        assert r["payroll"] == 0 and r["pos_code"] in {p[0] for p in POSITIONS}
    assert hr.split(100) == [8, 22, 42, 28] and sum(hr.split(97)) == 97


def test_s4_families_deterministic() -> None:
    assert _by_target(investment, FULL) == _by_target(investment, FULL)
    assert _by_target(hr, FULL) == _by_target(hr, FULL)
