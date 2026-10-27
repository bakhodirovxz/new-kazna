from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from app.etl.synthetic import SyntheticConnector
from app.etl.synthetic.families import procurement
from app.etl.synthetic.model import SynthModel
from app.etl.synthetic.reference import BRANCHES, PROCUREMENT_SUBJECTS
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
