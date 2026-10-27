from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.dwh.dates import date_id
from app.dwh.targets import SCHEDULE_DOC_TYPE
from app.etl.synthetic import SyntheticConnector
from app.etl.synthetic.families import calendar, loans
from app.etl.synthetic.model import SynthModel
from app.etl.types import Window
from tests.etl_helpers import TEST_AS_OF


class CollectSink:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, Any]]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))


WINDOW = Window(date(2026, 1, 1), TEST_AS_OF)


def _schedule() -> list[dict[str, Any]]:
    sink = CollectSink()
    calendar.generate(SynthModel(7, TEST_AS_OF), WINDOW, sink)
    return [row for target, row in sink.rows if target == "fact_payment_plan"]


def test_schedule_rows_are_future_workdays_with_fixed_tax_days() -> None:
    rows = _schedule()
    assert rows
    lo, hi = date_id(TEST_AS_OF + timedelta(days=1)), date_id(TEST_AS_OF + timedelta(days=30))
    for row in rows:
        assert row["doc_type"] == SCHEDULE_DOC_TYPE
        assert lo <= row["date_id"] <= hi
        day = date(row["date_id"] // 10000, row["date_id"] // 100 % 100, row["date_id"] % 100)
        assert day.weekday() < 5
        assert isinstance(row["amount"], Decimal) and row["amount"] > 0
        if row["item_code"] == calendar.TAX_ITEM:
            assert day.day in (15, 25)
        if row["item_code"] == calendar.SALARY_ITEM:
            assert day.day in (10, 25)
    assert {r["item_code"] for r in rows} & set(calendar.CONTRACT_ITEMS)


def test_schedule_is_deterministic() -> None:
    assert _schedule() == _schedule()


def test_loan_schedule_amortises_to_zero() -> None:
    sink = CollectSink()
    loans.generate(SynthModel(7, TEST_AS_OF), WINDOW, sink)
    rows = [row for target, row in sink.rows if target == "fact_loan_schedule"]
    short = sorted((r for r in rows if r["loan_code"] == "LOAN-07"), key=lambda r: r["date_id"])
    assert short[0]["date_id"] == 20260115 and short[-1]["date_id"] == 20271215
    assert abs(short[-1]["balance"]) < Decimal("0.01")
    assert all(r["doc_type"] == "loan_schedule" and r["date_id"] % 100 == 15 for r in rows)
    grace = [r for r in rows if r["loan_code"] == "LOAN-01" and r["date_id"] < 20270101]
    assert grace and all(r["principal"] == 0 and r["interest"] > 0 for r in grace)


def test_extract_sums_counts_of_same_target() -> None:
    sink = CollectSink()
    stats = SyntheticConnector(seed=7, as_of=TEST_AS_OF).extract(WINDOW, sink)
    plans = sum(1 for target, _ in sink.rows if target == "fact_payment_plan")
    assert stats.by_target["fact_payment_plan"] == plans
    assert stats.by_target["fact_loan_schedule"] > 0
    assert stats.rows == len(sink.rows)
