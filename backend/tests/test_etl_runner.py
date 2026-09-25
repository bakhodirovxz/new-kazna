from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import get_engine
from app.dwh import builds
from app.dwh.dates import today_tashkent
from app.etl.db import etl_transaction
from app.etl.retry import call_with_retries
from app.etl.runner import EtlBusyError, Runner, compute_window
from app.etl.types import Mode, Window
from tests.etl_helpers import (
    STEP_NAMES,
    TEST_AS_OF,
    ListConnector,
    RecordingNotifier,
    branch_row,
    cash_row,
    new_source,
    new_tag,
    open_run,
    purge_source,
)

HISTORY = date(2024, 1, 1)


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def _rows(tag: str) -> dict[str, list[dict[str, Any]]]:
    b = branch_row(tag)
    return {"dim_branch": [b], "fact_cashflow": [cash_row("r1", 20260805, b["code"], 100)]}


def _run(connector: ListConnector, *, mode: Mode = Mode.FULL,
         notifier: RecordingNotifier | None = None, sleeps: list[float] | None = None):
    return Runner(connector, mode=mode, today=TEST_AS_OF, notifier=notifier or RecordingNotifier(),
                  sleep=(sleeps if sleeps is not None else []).append, rng=lambda: 0.5).run()


def _active() -> int | None:
    with etl_transaction() as conn:
        return builds.active_build(conn)


def _run_row(run_id: int) -> dict[str, Any]:
    with etl_transaction() as conn:
        return dict(conn.execute(text("SELECT * FROM core.etl_run WHERE id = :r"),
                                 {"r": run_id}).mappings().one())


def _step_detail(run_id: int, name: str) -> dict[str, Any]:
    with etl_transaction() as conn:
        return dict(conn.execute(
            text("SELECT detail FROM core.etl_step WHERE run_id = :r AND name = :n"),
            {"r": run_id, "n": name}).scalar_one())


def test_today_tashkent_is_utc_plus_five() -> None:
    assert today_tashkent(datetime(2026, 9, 30, 19, 30, tzinfo=UTC)) == date(2026, 10, 1)
    assert today_tashkent(datetime(2026, 9, 30, 18, 59, tzinfo=UTC)) == date(2026, 9, 30)


def test_compute_window_rules() -> None:
    today = date(2026, 9, 24)
    full = compute_window(Mode.FULL, today=today, history_start=HISTORY,
                          last_watermark=datetime(2026, 9, 20, tzinfo=UTC))
    assert full == Window(HISTORY, today)
    assert compute_window(Mode.INCREMENTAL, today=today, history_start=HISTORY,
                          last_watermark=None) == Window(HISTORY, today)
    recent = compute_window(Mode.INCREMENTAL, today=today, history_start=HISTORY,
                            last_watermark=datetime(2026, 9, 20, 3, tzinfo=UTC))
    assert recent == Window(date(2026, 8, 6), today)
    assert compute_window(Mode.INCREMENTAL, today=date(2024, 1, 10), history_start=HISTORY,
                          last_watermark=datetime(2024, 1, 9, tzinfo=UTC)).date_from == HISTORY


def test_window_covers_gap_since_old_watermark() -> None:
    """Oxirgi muvaffaqiyatli yuklash 3 oy oldin — oraliq o'tkazib yuborilmasligi kerak."""
    window = compute_window(Mode.INCREMENTAL, today=date(2026, 9, 24), history_start=HISTORY,
                            last_watermark=datetime(2026, 6, 10, tzinfo=UTC))
    assert window.date_from == date(2026, 4, 26)


def test_call_with_retries_pause_sequence_and_jitter() -> None:
    sleeps: list[float] = []
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("timeout")
        return "ok"

    assert call_with_retries(flaky, sleep=sleeps.append, rng=lambda: 1.0) == "ok"
    assert sleeps == pytest.approx([33.0, 132.0])


def test_successful_run_publishes_and_journals(source: str) -> None:
    notifier = RecordingNotifier()
    connector = ListConnector(source, _rows(new_tag()), totals={202608: Decimal("100")})
    result = _run(connector, notifier=notifier)
    assert result.status == "success" and result.build_id is not None
    assert _active() == result.build_id
    run = _run_row(result.run_id)  # type: ignore[arg-type]
    assert run["rows_in"] == 2 and run["rows_upserted"] >= 2
    assert run["watermark"] == connector.mark
    assert (run["window_from"], run["window_to"]) == (HISTORY, TEST_AS_OF)
    with etl_transaction() as conn:
        steps = conn.execute(text("SELECT name, status FROM core.etl_step WHERE run_id = :r "
                                  "ORDER BY id"), {"r": result.run_id}).all()
        staged = conn.execute(text("SELECT count(*) FROM stg.rows WHERE load_id = :r"),
                              {"r": result.run_id}).scalar_one()
    assert [tuple(s) for s in steps] == [(n, "success") for n in STEP_NAMES]
    assert staged == 0
    assert notifier.items == []
    with get_engine("app").connect() as conn:
        actions = list(conn.execute(
            text("SELECT action FROM core.audit_log WHERE object_type = 'etl_run' "
                 "AND object_id = :r ORDER BY id"), {"r": str(result.run_id)}).scalars())
    assert actions == ["etl.run.started", "etl.run.finished"]


def test_quality_failure_keeps_previous_build(source: str) -> None:
    tag = new_tag()
    first = _run(ListConnector(source, _rows(tag)))
    assert first.status == "success"
    notifier = RecordingNotifier()
    bad = ListConnector(source, _rows(tag), totals={202608: Decimal("150")})
    result = _run(bad, notifier=notifier)
    assert result.status == "failed_quality"
    assert _active() == first.build_id
    with etl_transaction() as conn:
        status = conn.execute(text("SELECT status FROM core.builds WHERE build_id = :b"),
                              {"b": result.build_id}).scalar_one()
        quality = conn.execute(text("SELECT status FROM core.etl_step WHERE run_id = :r "
                                    "AND name = 'quality'"), {"r": result.run_id}).scalar_one()
    assert (status, quality) == ("failed", "failed")
    assert notifier.kinds == ["etl_quality", "control_totals"]


def test_retries_with_injected_delays(source: str) -> None:
    sleeps: list[float] = []
    connector = ListConnector(source, _rows(new_tag()), fail_times=2)
    result = _run(connector, sleeps=sleeps)
    assert result.status == "success"
    assert sleeps == [30.0, 120.0]
    assert connector.calls == 3


def test_gives_up_after_three_retries(source: str) -> None:
    before = _active()
    sleeps: list[float] = []
    notifier = RecordingNotifier()
    connector = ListConnector(source, _rows(new_tag()), fail_times=10)
    result = _run(connector, sleeps=sleeps, notifier=notifier)
    assert result.status == "failed"
    assert sleeps == [30.0, 120.0, 480.0]
    assert connector.calls == 4
    assert notifier.kinds == ["etl_failed"]
    assert _active() == before
    assert "ConnectionError" in (_run_row(result.run_id)["error"] or "")  # type: ignore[arg-type]


def test_non_retryable_error_fails_immediately(source: str) -> None:
    sleeps: list[float] = []
    result = _run(ListConnector(source, _rows(new_tag()), fail_times=1, error=ValueError),
                  sleeps=sleeps)
    assert result.status == "failed" and sleeps == []
    assert "ValueError" in (result.error or "")


def test_unhealthy_source_is_retried_then_fails(source: str) -> None:
    sleeps: list[float] = []
    connector = ListConnector(source, _rows(new_tag()), healthy=False)
    result = _run(connector, sleeps=sleeps)
    assert result.status == "failed" and len(sleeps) == 3 and connector.calls == 0
    assert "ConnectorUnavailableError" in (result.error or "")


def test_concurrent_run_is_rejected(source: str) -> None:
    with get_engine("etl").connect() as other:
        other = other.execution_options(isolation_level="AUTOCOMMIT")
        other.execute(text("SELECT pg_advisory_lock(hashtext('ugk_etl'))"))
        try:
            with pytest.raises(EtlBusyError):
                _run(ListConnector(source, _rows(new_tag())))
        finally:
            other.execute(text("SELECT pg_advisory_unlock(hashtext('ugk_etl'))"))


def test_stale_running_run_is_marked_failed(source: str) -> None:
    stale = open_run(source)
    result = _run(ListConnector(source, _rows(new_tag())))
    assert result.status == "success"
    row = _run_row(stale)
    assert row["status"] == "failed"
    assert "Прервано" in row["error"]


def test_incremental_uses_last_success_watermark(source: str) -> None:
    tag = new_tag()
    mark = datetime(2026, 9, 20, 3, 0, tzinfo=UTC)
    connector = ListConnector(source, _rows(tag), mark=mark)
    assert _run(connector).status == "success"
    result = _run(connector, mode=Mode.INCREMENTAL)
    assert result.status == "success"
    run = _run_row(result.run_id)  # type: ignore[arg-type]
    assert run["window_from"] == date(2026, 8, 6)
    with etl_transaction() as conn:
        kept = conn.execute(text("SELECT count(*) FROM dwh.fact_cashflow WHERE src_system = :s"),
                            {"s": source}).scalar_one()
    assert kept == 1  # 2026-08-05 oynadan tashqarida — o'chirilmaydi


def test_success_with_row_errors_notifies_counts_only(source: str) -> None:
    """Controller ruling (task-8): merge tomonidan bloklovchi bo'lmagan kod bilan rad etilgan
    qatorlar (masalan `negative_amount`) sifat tekshiruvini to'xtatmaydi (faqat `missing_branch`/
    `missing_dim` bloklaydi, quality.py) — lekin ular ko'rinmas bo'lib qolmasligi kerak: son
    jurnalga (etl_step.detail) va xabarnomaga (faqat sonlar, xom qiymatlarsiz) yozilishi shart."""
    tag = new_tag()
    b = branch_row(tag)
    rows = {
        "dim_branch": [b],
        "fact_cashflow": [
            cash_row("ok1", 20260805, b["code"], 100),
            cash_row("neg1", 20260806, b["code"], -50),  # CHECK amount >= 0 -> negative_amount
        ],
    }
    notifier = RecordingNotifier()
    connector = ListConnector(source, rows)
    result = _run(connector, notifier=notifier)
    assert result.status == "success"
    detail = _step_detail(result.run_id, "facts")  # type: ignore[arg-type]
    assert detail["fact_cashflow"]["errors"] == 1
    assert notifier.kinds == ["etl_row_errors"]
    body = notifier.items[0].body
    assert "fact_cashflow" in body
    # faqat sonlar — xom qiymat (masalan salbiy summa) xabarga chiqmasligi kerak
    assert "-50" not in body
    assert str(b["inn"]) not in body
