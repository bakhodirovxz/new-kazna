import re
from collections import defaultdict
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from itertools import pairwise
from typing import Any

from sqlalchemy import text

from app.dwh.dates import date_id, month_id
from app.etl.db import etl_transaction
from app.etl.runner import Runner, RunResult
from app.etl.synthetic import SyntheticConnector
from app.etl.synthetic.model import HISTORY_START, SynthModel
from app.etl.synthetic.reference import (
    BANKS,
    BRANCHES,
    EXPENSE_ITEMS,
    FUNDS,
    INCOME_ITEMS,
    PO_STATUSES,
)
from app.etl.types import Mode, Window
from tests.etl_helpers import TEST_AS_OF


class CollectSink:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, Any]]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))


def test_reference_mirrors_prototype() -> None:
    assert [b.id for b in BRANCHES] == list(range(1, 17))
    assert BRANCHES[0].kind == "head" and BRANCHES[0].weight == 0
    capacity = {b.id: b.capacity for b in BRANCHES}
    assert (capacity[2], capacity[13], capacity[16]) == (666, 175, 21)
    assert len(BANKS) == 5 and len(INCOME_ITEMS) == 6 and len(EXPENSE_ITEMS) == 9
    assert [s for s, _ in PO_STATUSES] == [
        "черновик", "на согласовании", "утверждено", "отправлено в банк", "исполнено", "отклонено"]
    assert abs(sum(w for _, w in PO_STATUSES) - 1) < 1e-9
    assert len(FUNDS) == 4
    assert {e.activity for e in EXPENSE_ITEMS} == {"centralized", "operating", "investing"}
    assert all(i.code.startswith("PKM54-") for i in (*INCOME_ITEMS, *EXPENSE_ITEMS))


def _august(model: SynthModel) -> list[Any]:
    return [p for p in model.cash.postings if (p.day.year, p.day.month) == (2026, 8)]


def test_generation_is_deterministic_and_independent_of_as_of() -> None:
    a = SynthModel(7, date(2026, 9, 24))
    b = SynthModel(7, date(2026, 9, 30))
    assert _august(a) and _august(a) == _august(b)
    assert _august(SynthModel(8, date(2026, 9, 24))) != _august(a)


def test_current_month_is_partial() -> None:
    model = SynthModel(7, date(2026, 9, 10))
    assert max(p.day for p in model.cash.postings) <= date(2026, 9, 10)
    assert max(r.day for r in model.cash.balances) == date(2026, 9, 10)


def test_balance_identity_holds_in_model() -> None:
    model = SynthModel(7, TEST_AS_OF)
    totals: dict[tuple[int, date], Decimal] = defaultdict(Decimal)
    for row in model.cash.balances:
        totals[(row.branch_id, row.day)] += row.balance
    net: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
    turnover: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
    for p in model.cash.postings:
        net[(p.branch_id, month_id(p.day))] += p.amount if p.direction == "in" else -p.amount
        turnover[(p.branch_id, month_id(p.day))] += p.amount
    for branch in BRANCHES:
        days = sorted(d for (b, d) in totals if b == branch.id)
        for prev, cur in pairwise(days):
            key = (branch.id, month_id(cur))
            diff = totals[(branch.id, cur)] - totals[(branch.id, prev)] - net[key]
            assert abs(diff) <= turnover[key] * Decimal("0.004") + Decimal("0.05"), (branch.id, cur)


def test_extract_respects_window_and_reports_all_targets() -> None:
    connector = SyntheticConnector(seed=7, as_of=TEST_AS_OF)
    window = Window(date(2026, 8, 1), TEST_AS_OF)
    sink = CollectSink()
    stats = connector.extract(window, sink)
    assert set(stats.by_target) == {
        "dim_branch", "dim_item", "dim_counterparty", "dim_bank", "dim_nomenclature",
        "dim_source", "dim_object", "dim_contract", "dim_loan", "dim_position", "fx_rate",
        "fact_cashflow", "fact_balance", "fact_payment_plan", "fact_payment_order", "fact_debt",
        "fact_target_funds",
    }
    assert stats.by_target["dim_branch"] == 16 and stats.by_target["dim_bank"] == 80
    assert stats.rows == len(sink.rows)
    for target, row in sink.rows:
        if target == "fact_balance":
            assert date_id(date(2026, 7, 31)) <= row["date_id"] <= window.to_id
        elif target.startswith("fact_") or target == "fx_rate":
            assert window.contains_id(row["date_id"]), (target, row)
    totals = connector.control_totals(window)
    assert totals is not None and sorted(totals.cashflow_by_month) == [202608, 202609]


def test_full_synthetic_pipeline(synthetic_run: RunResult) -> None:
    assert synthetic_run.status == "success"
    with etl_transaction() as conn:
        branches = conn.execute(text(
            "SELECT count(*) FROM dwh.dim_branch WHERE src_system = 'synthetic'")).scalar_one()
        cash = conn.execute(text(
            "SELECT count(*) FROM dwh.fact_cashflow WHERE src_system = 'synthetic'")).scalar_one()
        encrypted = conn.execute(text(
            "SELECT count(*) FROM dwh.dim_counterparty WHERE src_system = 'synthetic' "
            "AND inn_enc IS NOT NULL AND inn_bidx IS NOT NULL")).scalar_one()
        statuses = set(conn.execute(text(
            "SELECT DISTINCT status FROM dwh.fact_payment_order "
            "WHERE src_system = 'synthetic'")).scalars())
        quality = conn.execute(text(
            "SELECT detail FROM core.etl_step WHERE run_id = :r AND name = 'quality'"),
            {"r": synthetic_run.run_id}).scalar_one()
        overdue = conn.execute(text(
            "SELECT count(*) FROM dwh.fact_debt WHERE src_system = 'synthetic' "
            "AND overdue_days > 90")).scalar_one()
    assert branches == 16 and encrypted == 16
    assert cash > 5000
    assert statuses == {s for s, _ in PO_STATUSES}
    assert all(v["ok"] for v in quality.values())
    assert overdue > 0  # «Просроченные договоры > 90 дней» qoidasi uchun ma'lumot bor


def test_incremental_rerun_changes_nothing(synthetic_run: RunResult) -> None:
    result = Runner(SyntheticConnector(seed=7, as_of=TEST_AS_OF, source="synthetic"),
                    mode=Mode.INCREMENTAL, today=TEST_AS_OF, sleep=lambda _: None).run()
    assert result.status == "success"
    with etl_transaction() as conn:
        run = conn.execute(text("SELECT window_from, rows_upserted FROM core.etl_run "
                                "WHERE id = :r"), {"r": result.run_id}).one()
    assert run.window_from == date(2026, 8, 10)
    assert run.rows_upserted == 0
    assert date(2024, 1, 1) == HISTORY_START


def _extract(as_of: date, window: Window, seed: int = 7) -> list[tuple[str, dict[str, Any]]]:
    sink = CollectSink()
    SyntheticConnector(seed=seed, as_of=as_of).extract(window, sink)
    return sink.rows


def test_month_rollover_changes_no_closed_period_row() -> None:
    # I1: as_of 24 sentyabr -> 5 oktyabr; oyna yopiq oylar (2024-01-01..2026-06-30) — BARCHA
    # oilalar (o'lchovlar ham: ular as_of'ga bog'liq emas) ayni bir xil bo'lishi shart.
    window = Window(date(2024, 1, 1), date(2026, 6, 30))
    before = _extract(date(2026, 9, 24), window)
    after = _extract(date(2026, 10, 5), window)
    assert {t for t, _ in before} >= {"fact_debt", "fact_payment_order", "fact_balance",
                                      "fact_cashflow", "fx_rate", "dim_contract"}
    assert before == after


def test_current_month_orders_never_move_between_days() -> None:
    window = Window(date(2026, 9, 1), date(2026, 9, 30))
    early = {r["src_id"]: r["date_id"] for t, r in _extract(date(2026, 9, 10), window)
             if t == "fact_payment_order"}
    late = {r["src_id"]: r["date_id"] for t, r in _extract(date(2026, 9, 24), window)
            if t == "fact_payment_order"}
    assert early and len(late) > len(early)
    assert all(late[k] == v for k, v in early.items())


def test_no_negative_account_balances_across_seeds() -> None:
    for seed in (1, 2, 3, 7, 11, 42):
        for as_of in (TEST_AS_OF, date(2026, 9, 2), date(2025, 3, 3)):
            model = SynthModel(seed, as_of)
            assert min(row.balance for row in model.cash.balances) >= 0, (seed, as_of)


def test_mid_month_window_still_carries_opening_balance() -> None:
    rows = _extract(TEST_AS_OF, Window(date(2026, 8, 10), TEST_AS_OF))
    assert 20260731 in {r["date_id"] for t, r in rows if t == "fact_balance"}


def test_fx_rates_stop_at_as_of() -> None:
    rows = _extract(date(2026, 9, 24), Window(date(2026, 9, 20), date(2026, 9, 30)))
    assert max(r["date_id"] for t, r in rows if t == "fx_rate") == 20260924


def test_synthetic_identifiers_use_reserved_prefixes() -> None:
    rows = _extract(TEST_AS_OF, Window(date(2026, 9, 1), TEST_AS_OF))
    inns = [r["inn"] for t, r in rows if t in ("dim_branch", "dim_counterparty")]
    accounts = [r["account_number"] for t, r in rows if t == "dim_bank"]
    assert len(inns) == 16 + 16 and len(accounts) == 80 and len(set(accounts)) == 80
    assert all(re.fullmatch(r"999\d{6}", v) for v in inns)
    assert all(re.fullmatch(r"99999\d{15}", v) for v in accounts)


def test_control_totals_match_staged_cashflow() -> None:
    connector = SyntheticConnector(seed=7, as_of=TEST_AS_OF)
    window = Window(date(2025, 1, 1), TEST_AS_OF)
    sink = CollectSink()
    connector.extract(window, sink)
    staged: dict[int, Decimal] = defaultdict(Decimal)
    for target, row in sink.rows:
        if target == "fact_cashflow":
            staged[row["date_id"] // 100] += row["amount"]
    totals = connector.control_totals(window)
    assert totals is not None and dict(totals.cashflow_by_month) == dict(staged)


def test_sensitive_dim_columns_are_encrypted(synthetic_run: RunResult) -> None:
    with etl_transaction() as conn:
        banks = conn.execute(text(
            "SELECT account_enc, account_bidx FROM dwh.dim_bank WHERE src_system = 'synthetic'"
        )).all()
    assert len(banks) == 80
    assert all(enc is not None and bidx is not None for enc, bidx in banks)
    assert all(not bytes(enc).startswith(b"99999") and not re.search(rb"99999\d{15}", bytes(enc))
               for enc, _ in banks)


def test_published_synthetic_activates_its_build(published_synthetic: int) -> None:
    with etl_transaction() as conn:
        active = conn.execute(
            text("SELECT active_build_id FROM core.data_version WHERE id = 1")).scalar_one()
    assert active == published_synthetic
