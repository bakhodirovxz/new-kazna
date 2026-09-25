from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import get_engine
from app.dwh import builds
from app.dwh.dates import today_tashkent
from app.etl.db import etl_transaction
from app.etl.errors import safe_error
from app.etl.retry import NON_RETRYABLE, call_with_retries
from app.etl.runner import EtlBusyError, Runner, compute_window
from app.etl.types import ControlTotals, ExtractStats, HealthResult, Mode, Watermark, Window
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


class _WatermarkFlaky:
    """`ListConnector`ni o'raydi — faqat `watermark()`ni ma'lum marta muvaffaqiyatsiz qiladi
    (findings r1, I3: watermark() endi retry birligi ichida, alohida sinovdan o'tkaziladi)."""

    def __init__(self, inner: ListConnector, *, fail_times: int = 0) -> None:
        self.inner = inner
        self.fail_times = fail_times
        self.calls = 0

    @property
    def source(self) -> str:
        return self.inner.source

    def healthcheck(self) -> HealthResult:
        return self.inner.healthcheck()

    def watermark(self) -> Watermark:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError("время недоступно")
        return self.inner.watermark()

    def extract(self, window: Window, sink: Any) -> ExtractStats:
        return self.inner.extract(window, sink)

    def control_totals(self, window: Window) -> ControlTotals | None:
        return self.inner.control_totals(window)


class _SpyLog:
    """`app.etl.runner.log`ni almashtiradi — I1: strukturali logga UZATILGAN maydonlarda
    (haqiqiy renderlangan chiqish emas, lekin xuddi shu ma'lumot) xom qiymat yo'qligini
    tekshirish uchun. Haqiqiy structlog/stdout bilan ishlash global holatga ta'sir qiladi va
    keyingi testlarni buzadi (PrintLoggerFactory pytest capsys tomonidan yopilgan fayl
    ob'ektini ushlab qoladi) — shu sabab shu yerda oddiy spy ishlatiladi."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def error(self, event: str, **kw: Any) -> None:
        self.calls.append(("error", event, kw))

    def warning(self, event: str, **kw: Any) -> None:
        self.calls.append(("warning", event, kw))

    @property
    def blob(self) -> str:
        return " ".join(f"{level} {event} {kw}" for level, event, kw in self.calls)


class _RaisingConnector:
    """Har doim berilgan istisnoni `extract()`da ko'taradi — I1: xom xato matni hech qayerga
    (xabarnoma, jurnal, log) chiqmasligini tekshirish uchun."""

    def __init__(self, source: str, exc: Exception) -> None:
        self.source = source
        self.exc = exc

    def healthcheck(self) -> HealthResult:
        return HealthResult(True, "test")

    def watermark(self) -> Watermark:
        return Watermark(datetime(2026, 9, 24, 3, 0, tzinfo=UTC))

    def extract(self, window: Window, sink: Any) -> ExtractStats:
        raise self.exc

    def control_totals(self, window: Window) -> ControlTotals | None:
        return None


def _rows(tag: str) -> dict[str, list[dict[str, Any]]]:
    b = branch_row(tag)
    return {"dim_branch": [b], "fact_cashflow": [cash_row("r1", 20260805, b["code"], 100)]}


def _run(connector: Any, *, mode: Mode = Mode.FULL,
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


def _build_status(build_id: int) -> str:
    with etl_transaction() as conn:
        return str(conn.execute(text("SELECT status FROM core.builds WHERE build_id = :b"),
                                {"b": build_id}).scalar_one())


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


def test_non_os_errors_excluded_from_retry() -> None:
    """Findings r1, M8: fayl/ruxsat xatolari `OSError` kichik sinfi bo'lsa ham qayta
    urinilmaydi — doimiy muhit xatosi, holat qayta urinish bilan o'zgarmaydi."""
    sleeps: list[float] = []
    for exc_type in NON_RETRYABLE:
        def flaky(exc_type: type[Exception] = exc_type) -> None:
            raise exc_type("doimiy xato")

        with pytest.raises(exc_type):
            call_with_retries(flaky, sleep=sleeps.append, rng=lambda: 0.5)
    assert sleeps == []


def test_call_with_retries_rejects_invalid_jitter() -> None:
    with pytest.raises(ValueError, match="jitter"):
        call_with_retries(lambda: None, jitter=1.0)
    with pytest.raises(ValueError, match="jitter"):
        call_with_retries(lambda: None, jitter=-0.01)


def test_safe_error_hides_dbapi_error_message_and_detail() -> None:
    """Findings r1, I1: DB DETAIL'ida xom qiymat bo'lgan taqlidiy IntegrityError — faqat sinf
    nomi + SQLSTATE qaytishi kerak, drayver xabari yoki DETAIL HECH QACHON emas."""

    class _FakeOrigError(Exception):
        sqlstate = "23505"

    secret = "Key (inn_bidx)=(\\x1234abcd) already exists."
    orig = _FakeOrigError(f"duplicate key value violates unique constraint DETAIL: {secret}")
    exc = DBAPIError("INSERT INTO dwh.dim_counterparty ...", {}, orig)
    result = safe_error(exc)
    assert secret not in result
    assert "DETAIL" not in result
    assert "DBAPIError" in result and "23505" in result


def test_successful_run_publishes_and_journals(source: str) -> None:
    notifier = RecordingNotifier()
    connector = ListConnector(source, _rows(new_tag()), totals={202608: Decimal("100")})
    result = _run(connector, notifier=notifier)
    assert result.status == "success" and result.build_id is not None
    assert result.journal_failed is False
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


def test_quality_failure_with_row_errors_notes_publication_blocked(source: str) -> None:
    """Findings r1, M6: `etl_row_errors` xabari nashr HOLATINI aytishi kerak — bu holatda
    sifat tekshiruvi muvaffaqiyatsiz (control_totals) va bitta qator ham rad etilgan."""
    tag = new_tag()
    b = branch_row(tag)
    rows = {
        "dim_branch": [b],
        "fact_cashflow": [
            cash_row("ok1", 20260805, b["code"], 100),
            cash_row("neg1", 20260806, b["code"], -50),  # negative_amount, bloklamaydi
        ],
    }
    notifier = RecordingNotifier()
    connector = ListConnector(source, rows, totals={202608: Decimal("999")})
    result = _run(connector, notifier=notifier)
    assert result.status == "failed_quality"
    assert notifier.kinds == ["etl_quality", "control_totals", "etl_row_errors"]
    body = notifier.items[-1].body
    assert "заблокирована" in body
    assert "Отклонено строк (ошибки): 1" in body
    assert "-50" not in body


def test_retries_with_injected_delays(source: str) -> None:
    sleeps: list[float] = []
    connector = ListConnector(source, _rows(new_tag()), fail_times=2)
    result = _run(connector, sleeps=sleeps)
    assert result.status == "success"
    assert sleeps == [30.0, 120.0]
    assert connector.calls == 3
    detail = _step_detail(result.run_id, "extract")  # type: ignore[arg-type]
    assert len(detail["retries"]) == 2


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
    row = _run_row(result.run_id)  # type: ignore[arg-type]
    assert "ConnectionError" in (row["error"] or "")
    assert row["watermark"] is None  # M10: give-up holatida watermark yozilmaydi
    detail = _step_detail(result.run_id, "extract")  # type: ignore[arg-type]
    assert len(detail["retries"]) == 3  # M10: give-up holatida ham qayta urinishlar jurnali


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


def test_flaky_watermark_is_retried_inside_extract_step(source: str) -> None:
    """Findings r1, I3: `watermark()` xatosi ham qayta urinish birligi ICHIDA — alohida,
    himoyalanmagan chaqiruv sifatida emas."""
    tag = new_tag()
    inner = ListConnector(source, _rows(tag))
    connector = _WatermarkFlaky(inner, fail_times=2)
    sleeps: list[float] = []
    result = _run(connector, sleeps=sleeps)
    assert result.status == "success"
    assert sleeps == [30.0, 120.0]
    assert connector.calls == 3
    assert inner.calls == 1  # extract() faqat muvaffaqiyatli (oxirgi) urinishda chaqiriladi
    detail = _step_detail(result.run_id, "extract")  # type: ignore[arg-type]
    assert len(detail["retries"]) == 2


def test_raw_exception_text_never_leaks(source: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Findings r1, I1: konnektor ko'targan xom xato matni (masalan INN/hisob raqami
    substring'lari) hech qayerga — xabarnoma, `etl_run.error`, `etl_step.detail`, strukturali
    log chiqishi — sizib chiqmasligi kerak."""
    spy = _SpyLog()
    monkeypatch.setattr("app.etl.runner.log", spy)
    secret_inn = "123456789"
    secret_acct = "20208000900123456789"
    connector = _RaisingConnector(source, ValueError(f"bad INN {secret_inn} acct {secret_acct}"))
    notifier = RecordingNotifier()
    result = _run(connector, notifier=notifier)
    assert result.status == "failed"
    with etl_transaction() as conn:
        step_detail_text = conn.execute(text(
            "SELECT detail::text FROM core.etl_step WHERE run_id = :r AND name = 'extract'"),
            {"r": result.run_id}).scalar_one()
    run_error = _run_row(result.run_id)["error"] or ""  # type: ignore[arg-type]
    haystacks = [result.error or "", run_error, step_detail_text, spy.blob,
                 *(f"{n.subject}\n{n.body}" for n in notifier.items)]
    for blob in haystacks:
        assert secret_inn not in blob
        assert secret_acct not in blob
    assert "ValueError" in (result.error or "")
    assert notifier.kinds == ["etl_failed"]


def test_notify_fires_even_if_finish_journal_fails(source: str,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """Findings r1, I2: xabarnoma HAR DOIM birinchi yuboriladi — keyingi jurnal yozuvi
    muvaffaqiyatsiz (yoki hatto istisno ko'targan) bo'lsa ham."""
    notifier = RecordingNotifier()
    connector = ListConnector(source, _rows(new_tag()), fail_times=10)
    runner = Runner(connector, mode=Mode.FULL, today=TEST_AS_OF, notifier=notifier,
                    sleep=[].append, rng=lambda: 0.5)

    def boom(self: Runner, *args: Any, **kwargs: Any) -> bool:
        raise RuntimeError("journal boom")

    monkeypatch.setattr(Runner, "_finish", boom)
    result = runner.run()
    assert result.status == "failed"
    assert notifier.kinds == ["etl_failed"]
    assert result.journal_failed is True


def test_success_survives_audit_failure(source: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Findings r1, I2: nashrdan keyingi audit yozuvi muvaffaqiyatsiz bo'lsa ham `run()`
    muvaffaqiyatli natijani qaytarishi va build faol bo'lishi kerak."""
    connector = ListConnector(source, _rows(new_tag()))
    runner = Runner(connector, mode=Mode.FULL, today=TEST_AS_OF, notifier=RecordingNotifier(),
                    sleep=[].append, rng=lambda: 0.5)

    def boom(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("audit boom")

    monkeypatch.setattr("app.etl.runner.record", boom)
    result = runner.run()
    assert result.status == "success" and result.build_id is not None
    assert _active() == result.build_id
    assert result.journal_failed is True


def test_exception_in_quality_marks_build_failed(source: str,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    first = _run(ListConnector(source, _rows(new_tag())))
    assert first.status == "success"
    before_active = _active()
    connector = ListConnector(source, _rows(new_tag()))
    runner = Runner(connector, mode=Mode.FULL, today=TEST_AS_OF, notifier=RecordingNotifier(),
                    sleep=[].append, rng=lambda: 0.5)

    def boom(self: Runner, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("quality boom")

    monkeypatch.setattr(Runner, "_quality", boom)
    result = runner.run()
    assert result.status == "failed"
    assert _active() == before_active
    assert result.build_id is not None
    assert _build_status(result.build_id) == "failed"


def test_exception_in_publish_marks_build_failed(source: str,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    first = _run(ListConnector(source, _rows(new_tag())))
    assert first.status == "success"
    before_active = _active()
    connector = ListConnector(source, _rows(new_tag()))
    runner = Runner(connector, mode=Mode.FULL, today=TEST_AS_OF, notifier=RecordingNotifier(),
                    sleep=[].append, rng=lambda: 0.5)

    def boom(self: Runner, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("publish boom")

    monkeypatch.setattr(Runner, "_publish", boom)
    result = runner.run()
    assert result.status == "failed"
    assert _active() == before_active
    assert result.build_id is not None
    assert _build_status(result.build_id) == "failed"


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


def test_stale_running_run_also_fails_its_orphaned_build(source: str) -> None:
    """Findings r1, M5: o'lik yugurishga tegishli, hali nashr qilinmagan build ham darhol
    muvaffaqiyatsiz deb belgilanishi kerak — 7 kunlik tozalashni kutmasdan. (Yangi yugurish
    muvaffaqiyatli nashr qilingach, `builds.publish()` ichidagi `prune()` endi 'failed'
    holatidagi bu build'ni ham darhol o'chirishi mumkin — ikkalasi ham M5ning bajarilganini
    tasdiqlaydi: faqat 'building'/'ready' holatida OSILIB QOLMAGAN bo'lishi muhim.)"""
    stale = open_run(source)
    with etl_transaction() as conn:
        orphan_build_id = builds.create_build(conn, stale)
        builds.mark_ready(conn, orphan_build_id)
    result = _run(ListConnector(source, _rows(new_tag())))
    assert result.status == "success"
    with etl_transaction() as conn:
        status = conn.execute(text("SELECT status FROM core.builds WHERE build_id = :b"),
                              {"b": orphan_build_id}).scalar_one_or_none()
    assert status in (None, "failed")


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
    jurnalga (etl_step.detail) va xabarnomaga (faqat sonlar, xom qiymatlarsiz) yozilishi shart.
    Findings r1, M6: sonlar alohida qatorlarda, nashr holati ("выполнена") aniq aytiladi."""
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
    assert "Отклонено строк (ошибки): 1" in body
    assert "Предупреждения: 0" in body
    assert "выполнена" in body
    # faqat sonlar — xom qiymat (masalan salbiy summa) xabarga chiqmasligi kerak
    assert "-50" not in body
    assert str(b["inn"]) not in body
