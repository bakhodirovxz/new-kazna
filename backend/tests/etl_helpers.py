"""ETL testlari uchun yordamchilar: har test o'z `src_system` manbasi va test filiali bilan
ishlaydi va oxirida o'zi yaratgan qatorlarni o'chiradi (sintetik ma'lumotga tegmaydi)."""

from __future__ import annotations

import uuid
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.dwh import builds
from app.dwh.aggregates import BuildParams, build_all
from app.dwh.targets import OTHER_OUT_ITEM
from app.etl.db import etl_transaction
from app.etl.merge import MergeStats, merge_dims, merge_facts
from app.etl.notify import Notification
from app.etl.staging import DbStagingSink, clear_load
from app.etl.types import ControlTotals, ExtractStats, HealthResult, StagingSink, Watermark, Window

TEST_AS_OF = date(2026, 9, 24)
FULL_WINDOW = Window(date(2024, 1, 1), TEST_AS_OF)

# O'chirish tartibi: faktlar → bog'liq o'lchovlar → asosiy o'lchovlar.
_PURGE_ORDER = (
    "fact_cashflow", "fact_balance", "fact_payment_plan", "fact_payment_order", "fact_debt",
    "fact_generation", "fact_energy_sales", "fact_procurement", "fact_stock", "fact_stock_move",
    "fact_investment", "fact_loan_schedule", "fact_hr", "fact_target_funds", "fx_rate",
    "dim_contract", "dim_loan", "dim_object", "dim_branch", "dim_item", "dim_counterparty",
    "dim_bank", "dim_nomenclature", "dim_source", "dim_position",
)


def new_source() -> str:
    return f"t{uuid.uuid4().hex[:10]}"


def new_tag() -> str:
    return uuid.uuid4().hex[:6].upper()


def open_run(source: str) -> int:
    with etl_transaction() as conn:
        return int(conn.execute(
            text("INSERT INTO core.etl_run (source, mode, status) "
                 "VALUES (:s, 'full', 'running') RETURNING id"), {"s": source}).scalar_one())


def stage(
    load_id: int, source: str, rows: Mapping[str, Sequence[Mapping[str, Any]]]
) -> dict[str, int]:
    with etl_transaction() as conn:
        clear_load(conn, load_id)
        sink = DbStagingSink(conn, load_id, source)
        for target, items in rows.items():
            for row in items:
                sink.add(target, row)
        return sink.close()


def merge_all(load_id: int, source: str, window: Window = FULL_WINDOW, *,
              complete: Collection[str] = (), as_of: date = TEST_AS_OF) -> list[MergeStats]:
    with etl_transaction() as conn:
        stats = merge_dims(conn, load_id=load_id, source=source, as_of=as_of)
        stats += merge_facts(conn, load_id=load_id, source=source, window=window,
                             complete=complete, as_of=as_of)
    return stats


def purge_source(source: str) -> None:
    with etl_transaction() as conn:
        conn.execute(text(
            "DELETE FROM dwh.dim_branch_version WHERE branch_id IN "
            "(SELECT branch_id FROM dwh.dim_branch WHERE src_system = :s)"), {"s": source})
        conn.execute(text(
            "DELETE FROM dwh.dim_loan_version WHERE loan_id IN "
            "(SELECT loan_id FROM dwh.dim_loan WHERE src_system = :s)"), {"s": source})
        for table in _PURGE_ORDER:
            conn.execute(text(f"DELETE FROM dwh.{table} WHERE src_system = :s"), {"s": source})
        conn.execute(text(
            "DELETE FROM core.builds b WHERE b.load_id IN "
            "(SELECT id FROM core.etl_run WHERE source = :s) AND b.build_id IS DISTINCT FROM "
            "(SELECT active_build_id FROM core.data_version WHERE id = 1)"), {"s": source})
        conn.execute(text(
            "DELETE FROM stg.rows WHERE load_id IN "
            "(SELECT id FROM core.etl_run WHERE source = :s)"), {"s": source})


def branch_row(tag: str, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "code": f"T-{tag}", "name": f"Тестовая ГЭС {tag}", "short_name": f"Т{tag}",
        "inn": "123456789", "kind": "ges", "capacity_mw": 100, "lat": 41.0, "lon": 69.0,
        "sort_order": 99,
    }
    row.update(overrides)
    return row


def cash_row(
    src_id: str, date_id: int, branch_code: str, amount: float, *,
    direction: str = "out", item_code: str = OTHER_OUT_ITEM, **extra: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "doc_type": "bank_entry", "src_id": src_id, "date_id": date_id,
        "branch_code": branch_code, "item_code": item_code, "direction": direction,
        "amount": amount, "gl_account": "5110",
    }
    row.update(extra)
    return row


def load_and_build(
    source: str, rows: Mapping[str, Sequence[Mapping[str, Any]]], *,
    window: Window = FULL_WINDOW,
) -> tuple[int, int]:
    """Staging → merge → yangi build (publish qilinmaydi). (run_id, build_id) qaytaradi."""
    run_id = open_run(source)
    stage(run_id, source, rows)
    merge_all(run_id, source, window)
    with etl_transaction() as conn:
        build_id = builds.create_build(conn, run_id)
        build_all(conn, build_id, BuildParams(as_of=TEST_AS_OF, date_from=window.date_from))
        builds.mark_ready(conn, build_id)
    return run_id, build_id


STEP_NAMES = ("extract", "dims", "facts", "aggregates", "quality", "publish")


@dataclass
class ListConnector:
    """Oldindan berilgan qatorlarni qaytaruvchi konnektor; nosozliklarni simulyatsiya qiladi."""

    source: str
    rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    totals: dict[int, Decimal] | None = None
    fail_times: int = 0
    error: type[Exception] = ConnectionError
    healthy: bool = True
    mark: datetime = field(default_factory=lambda: datetime(2026, 9, 24, 3, 0, tzinfo=UTC))
    calls: int = 0

    def healthcheck(self) -> HealthResult:
        return HealthResult(self.healthy, "test")

    def watermark(self) -> Watermark:
        return Watermark(self.mark)

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.error("источник недоступен")
        counts: dict[str, int] = {}
        for target, items in self.rows.items():
            counts[target] = 0
            for row in items:
                if target.startswith("fact_") and not window.contains_id(int(row["date_id"])):
                    continue
                sink.add(target, row)
                counts[target] += 1
        return ExtractStats(sum(counts.values()), counts)

    def control_totals(self, window: Window) -> ControlTotals | None:
        return None if self.totals is None else ControlTotals(self.totals)


class RecordingNotifier:
    def __init__(self) -> None:
        self.items: list[Notification] = []

    def notify(self, notification: Notification) -> None:
        self.items.append(notification)

    @property
    def kinds(self) -> list[str]:
        return [n.kind for n in self.items]
