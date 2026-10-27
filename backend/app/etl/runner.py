"""ETL runner (spec 5.1): PostgreSQL advisory lock bilan bitta vaqtda bitta yuklash.

Pipeline: extract -> dims -> facts -> aggregates -> quality -> publish. Istalgan qadam xatosi
yoki sifat buzilishi -> publish yo'q, oldingi build aktiv qoladi, notifier chaqiriladi.
Har qadam core.etl_step ga, yuklash core.etl_run ga, boshlanish/tugash auditga yoziladi.

Task-8 amendments (A8.1/A8.2): `AuditEvent.result` — `Literal["ok","fail","denied"]`
(app/audit/service.py) — `_audit()` shu turdagi parametr oladi (mypy strict); `record()`
`role="etl"` bilan chaqiriladi — worker `ugk_etl` ulanishi orqali audit yozadi.

Findings round 1 (task-8-findings-r1.md) — bu modulda qo'llanilgan majburiy tuzatishlar:
- I1: xom istisno matni (DB DETAIL, konnektor xabari, manba qiymati) hech qachon
  xabarnoma/jurnal/logga chiqmaydi — `app.etl.errors.safe_error()`/`is_safe()`/`sqlstate_of()`
  ishlatiladi; DB/konnektor xatolari uchun `exc_info` hech qachon yozilmaydi.
- I2: xabarnoma HAR DOIM birinchi (`_notify`, himoyalangan), keyin jurnal/audit alohida
  himoyalangan (`_finish`/`_audit` hech qachon `run()`ni yiqitmaydi — `journal_failed` bayrog'i).
- I3: `connector.watermark()` endi qayta urinish birligi ICHIDA (`_extract`ning `once()`si) —
  alohida, himoyalanmagan chaqiruv sifatida emas.
- M4: qulfni bo'shatish xatosi `finally`da ushlanadi va sinf nomi bilan loglanadi.
- M5: "running" holatida qolib ketgan yuklashlar uchun ularning tugallanmagan (building/ready)
  buildlari ham `mark_failed` qilinadi.
- M6/M7: `etl_row_errors` matni sonlarni ajratadi, nashr holatini aytadi; barcha
  `notifier.notify` chaqiruvlari himoyalangan.
- M8: `app.etl.retry.NON_RETRYABLE` (fayl/ruxsat xatolari) qayta urinilmaydi.

Controller ruling (task-8, extra requirement): `app/etl/merge.py` bloklovchi bo'lmagan kod
bilan rad etgan qatorlar sifat tekshiruvini to'xtatmaydi — ular baribir ko'rinishi kerak:
(1) har maqsad bo'yicha xato/ogohlantirish soni `core.etl_step.detail`da, (2) agar jami xato
> 0 bo'lsa — xabarnomada, FAQAT sonlar bilan (xom qiymat, INN, hisob raqami, bank kodi,
kontragent nomi yoki `*_enc` HECH QACHON yozilmaydi).
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text

from app.audit.service import AuditAction, AuditEvent, AuditResult, record
from app.core.db import get_engine
from app.core.logging import get_logger
from app.dwh import builds
from app.dwh.aggregates import BuildParams, build_all
from app.dwh.dates import TASHKENT, add_months, month_start, today_tashkent
from app.dwh.reference import current_setting
from app.etl.db import etl_transaction
from app.etl.errors import (
    EtlBusyError,
    EtlConfigError,
    QualityContextError,
    is_safe,
    safe_error,
    sqlstate_of,
)
from app.etl.merge import MergeStats, merge_dims, merge_facts
from app.etl.notify import LogNotifier, Notification, Notifier
from app.etl.quality import CheckResult, failed, run_checks
from app.etl.retry import RETRY_DELAYS, call_with_retries
from app.etl.staging import DbStagingSink, clear_load
from app.etl.types import (
    ConnectorUnavailableError,
    ExtractStats,
    Mode,
    SourceConnector,
    Watermark,
    Window,
)

__all__ = ["ETL_LOCK", "EtlBusyError", "RunResult", "Runner", "StepResult", "compute_window"]

ETL_LOCK = "ugk_etl"
AGGREGATE_YEARS = 10  # spec 4.7: agregatlar 10 yil saqlanadi
log = get_logger("ugekazna.etl")


@dataclass(frozen=True, slots=True)
class RunResult:
    run_id: int | None
    status: str
    build_id: int | None = None
    error: str | None = None
    # I2/M-conv: jurnal (core.etl_run yozuvi) yoki audit yozuvlaridan biri muvaffaqiyatsiz
    # bo'lsa ham `run()` HECH QACHON ko'tarilmaydi — shu holat shu yerda bayon qilinadi
    # (pipeline'ning o'zi — extract/dims/facts/aggregates/quality/publish — muvaffaqiyatli
    # bo'lgan bo'lishi mumkin, faqat KUZATUV yozuvi to'liq bo'lmagan).
    journal_failed: bool = False


@dataclass
class StepResult:
    rows: int = 0
    detail: dict[str, Any] = field(default_factory=dict)
    value: Any = None
    ok: bool = True


class _BufferSink:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, Any]]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))


class _StepDetailError(Exception):
    """Ichki (faqat `_extract`/`_step` orasida): asl xato + shu paytgacha to'plangan
    tafsilot (masalan qayta urinishlar jurnali) — findings r1 M10: qayta urinishlar soni
    yuklash butunlay muvaffaqiyatsiz bo'lganda ham (give-up) `core.etl_step.detail`da
    yo'qolib qolmasligi kerak. `_step()` buni ushlab, tafsilotni umumiy `{"error": ...}`ga
    birlashtiradi, so'ng ASL istisnoni qayta ko'taradi (chaqiruvchi kod uni ko'rmaydi)."""

    def __init__(self, cause: BaseException, detail: dict[str, Any]) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.detail = detail


def compute_window(mode: Mode, *, today: date, history_start: date,
                   last_watermark: datetime | None, lookback_days: int = 45) -> Window:
    """To'liq: tarix boshidan. Inkremental: min(watermark - lookback_days, joriy oy boshi) --
    TZ: "последние 45 дней плюс текущий месяц целиком" (standart 45)."""
    if mode == Mode.FULL or last_watermark is None:
        return Window(history_start, today)
    wm_day = last_watermark.astimezone(TASHKENT).date()
    start = min(wm_day - timedelta(days=lookback_days), month_start(today))
    return Window(max(start, history_start), today)


def _merge_result(stats: list[MergeStats]) -> StepResult:
    detail = {
        s.target: {"upserted": s.upserted, "deleted": s.deleted, "errors": s.errors,
                   "warnings": s.warnings}
        for s in stats
    }
    return StepResult(sum(s.upserted for s in stats), detail, stats)


def _log_failure(event: str, exc: BaseException, **fields: Any) -> None:
    # I1: DB/drayver/konnektor yoki noma'lum xatolar uchun `exc_info` HECH QACHON — faqat
    # sinf nomi + (agar bo'lsa) SQLSTATE; faqat BIZNING xavfsiz turlarimiz uchun to'liq
    # traceback foydali va xavfsiz (xabarlari faqat ID/kod).
    log.error(event, error_class=type(exc).__name__, sqlstate=sqlstate_of(exc),
             exc_info=exc if is_safe(exc) else None, **fields)


class Runner:
    def __init__(
        self,
        connector: SourceConnector,
        *,
        mode: Mode = Mode.INCREMENTAL,
        notifier: Notifier | None = None,
        today: date | None = None,
        sleep: Callable[[float], None] = time.sleep,
        delays: Sequence[float] = RETRY_DELAYS,
        jitter: float = 0.1,
        rng: Callable[[], float] = random.random,  # kriptografik emas
        triggered_by: int | None = None,
    ) -> None:
        self.connector = connector
        self.mode = mode
        self.notifier = notifier or LogNotifier()
        self.today = today or today_tashkent()
        self.sleep = sleep
        self.delays = tuple(delays)
        self.jitter = jitter
        self.rng = rng
        self.triggered_by = triggered_by

    # -- Kirish nuqtasi --------------------------------------------------
    def run(self) -> RunResult:
        with get_engine("etl").connect() as raw:
            lock = raw.execution_options(isolation_level="AUTOCOMMIT")
            got = lock.execute(text("SELECT pg_try_advisory_lock(hashtext(:k))"),
                               {"k": ETL_LOCK}).scalar_one()
            if not got:
                raise EtlBusyError
            try:
                return self._run_locked()
            finally:
                close = getattr(self.connector, "close", None)
                if close is not None:  # masalan, 1C HTTP mijozi (ulanish oqib ketmasin)
                    try:
                        close()
                    except Exception as exc:
                        _log_failure("etl_connector_close_failed", exc)
                # M4: unlock xatosi natijani (yoki chiquvchi istisnoni) niqoblamasligi kerak.
                try:
                    lock.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": ETL_LOCK})
                except Exception as exc:
                    _log_failure("etl_unlock_failed", exc)

    # -- Pipeline ----------------------------------------------------------
    def _run_locked(self) -> RunResult:
        source = self.connector.source
        with etl_transaction() as conn:
            # Lock bizda -- "running" holatidagi har qanday yugurish o'lik (worker to'xtagan).
            stale_runs = list(conn.execute(text(
                "UPDATE core.etl_run SET status = 'failed', finished_at = now(), "
                "error = 'Прервано: процесс загрузки был остановлен' WHERE status = 'running' "
                "RETURNING id")).scalars())
            if stale_runs:
                # M5: o'sha o'lik yuklashlarga tegishli, hali nashr qilinmagan buildlar ham
                # muvaffaqiyatsiz deb belgilanadi — aks holda ular abadiy "building"/"ready"da
                # osilib qoladi (faqat 7 kunlik `prune()` ularni keyinroq tozalaydi).
                orphaned = list(conn.execute(
                    text("SELECT build_id FROM core.builds WHERE load_id = ANY(:runs) "
                         "AND status IN ('building', 'ready')"), {"runs": stale_runs}).scalars())
                for orphan_build_id in orphaned:
                    builds.mark_failed(conn, orphan_build_id)
            try:
                history_start = date.fromisoformat(str(current_setting(conn, "etl.history_start")))
                keep = int(current_setting(conn, "builds.keep"))
                fact_years = int(current_setting(conn, "retention.fact_years"))
                lookback = int(current_setting(conn, "etl.incremental_lookback_days"))
            except (KeyError, ValueError, TypeError) as exc:
                # I1: bu FAQAT bizning sozlamalarimizni o'qish/talqin qilishdagi dasturiy
                # xato — xabari faqat kalit/qiymat turi haqida, xavfsiz.
                raise EtlConfigError(str(exc)) from exc
            last = conn.execute(text(
                "SELECT watermark FROM core.etl_run WHERE source = :s AND status = 'success' "
                "AND watermark IS NOT NULL ORDER BY id DESC LIMIT 1"), {"s": source}).scalar()
            window = compute_window(self.mode, today=self.today, history_start=history_start,
                                    last_watermark=last, lookback_days=lookback)
            # S3: manba o'z oynasini cheklashi mumkin (1C ombori — oxirgi N oy snapshot'lari).
            # Almashtirish (replace) ham shu qisqa oyna ichida — undan eski qatorlar saqlanadi.
            months_back = getattr(self.connector, "lookback_months", None)
            if isinstance(months_back, int) and months_back > 0:
                floor = add_months(month_start(self.today), -(months_back - 1))
                window = Window(max(window.date_from, floor), window.date_to)
            run_id = int(conn.execute(text(
                "INSERT INTO core.etl_run (source, mode, status, window_from, window_to, "
                "triggered_by) VALUES (:s, :m, 'running', :f, :t, :u) RETURNING id"),
                {"s": source, "m": self.mode.value, "f": window.date_from, "t": window.date_to,
                 "u": self.triggered_by}).scalar_one())
        started_audit_ok = self._audit(AuditAction.ETL_RUN_STARTED, run_id, "ok",
                                       {"source": source, "mode": self.mode.value,
                                        "window": [window.date_from.isoformat(),
                                                   window.date_to.isoformat()]})

        build_id: int | None = None
        rows_in = rows_upserted = 0
        merge_stats: list[MergeStats] = []
        try:
            extract = self._step(run_id, "extract", lambda: self._extract(run_id, window))
            extracted: tuple[ExtractStats, Watermark] = extract.value
            stats, watermark = extracted
            rows_in = stats.rows
            dims = self._step(run_id, "dims", lambda: self._dims(run_id))
            facts = self._step(run_id, "facts",
                               lambda: self._facts(run_id, window, stats.by_target.keys()))
            rows_upserted = dims.rows + facts.rows
            merge_stats = [*dims.value, *facts.value]
            params = BuildParams(
                as_of=self.today,
                # Faktlar `fact_years` yil saqlanadi; undan eski oylar oldingi build'dan.
                date_from=max(history_start,
                              add_months(month_start(self.today), -12 * fact_years)),
                keep_from=add_months(month_start(self.today), -12 * AGGREGATE_YEARS),
            )
            aggregates = self._step(run_id, "aggregates",
                                    lambda: self._aggregates(run_id, params))
            build_id = int(aggregates.value)
            quality = self._step(run_id, "quality",
                                 lambda: self._quality(run_id, int(aggregates.value), window))
            bad: list[CheckResult] = quality.value
            if bad:
                return self._fail_quality(run_id, build_id, bad, rows_in, rows_upserted,
                                          merge_stats, started_audit_ok)
            self._step(run_id, "publish", lambda: self._publish(run_id, int(aggregates.value),
                                                                keep))
        except Exception as exc:  # yuklash xatosi jurnalga yoziladi, qayta ko'tarilmaydi
            _log_failure("etl_failed", exc, run_id=run_id, source=source)
            if build_id is not None:
                self._safe_mark_failed(build_id)
            error = safe_error(exc)
            # I2: xabarnoma HAR DOIM birinchi (himoyalangan), keyin jurnal — shunda jurnal
            # yozuvi muvaffaqiyatsiz bo'lsa ham xabarnoma allaqachon yetkazilgan bo'ladi.
            self._notify(Notification(
                "etl_failed", f"Загрузка «{source}» завершилась ошибкой",
                f"Запуск №{run_id}, режим {self.mode.value}.\nОшибка: {error}"))
            journal_ok = self._finish_safely(run_id, "failed", build_id, rows_in, rows_upserted,
                                             None, error)
            return RunResult(run_id, "failed", build_id, error,
                             journal_failed=not (started_audit_ok and journal_ok))
        self._notify_row_errors(run_id, merge_stats, published=True)
        journal_ok = self._finish_safely(run_id, "success", build_id, rows_in, rows_upserted,
                                         watermark.value, None)
        return RunResult(run_id, "success", build_id,
                         journal_failed=not (started_audit_ok and journal_ok))

    def _step(self, run_id: int, name: str, fn: Callable[[], StepResult]) -> StepResult:
        with etl_transaction() as conn:
            step_id = conn.execute(text(
                "INSERT INTO core.etl_step (run_id, name, status) VALUES (:r, :n, 'running') "
                "RETURNING id"), {"r": run_id, "n": name}).scalar_one()
        try:
            result = fn()
        except _StepDetailError as exc:
            _log_failure("etl_step_failed", exc.cause, run_id=run_id, step=name)
            self._fail_step(step_id, exc.cause, exc.detail)
            raise exc.cause from exc
        except Exception as exc:
            _log_failure("etl_step_failed", exc, run_id=run_id, step=name)
            self._fail_step(step_id, exc, {})
            raise
        with etl_transaction() as conn:
            conn.execute(text(
                "UPDATE core.etl_step SET status = :st, finished_at = now(), rows = :n, "
                "detail = CAST(:d AS jsonb) WHERE id = :i"),
                {"i": step_id, "st": "success" if result.ok else "failed", "n": result.rows,
                 "d": json.dumps(result.detail, ensure_ascii=False, default=str)})
        return result

    def _fail_step(self, step_id: int, exc: BaseException, extra: dict[str, Any]) -> None:
        detail = {"error": safe_error(exc), **extra}
        try:
            with etl_transaction() as conn:
                conn.execute(text(
                    "UPDATE core.etl_step SET status = 'failed', finished_at = now(), "
                    "detail = CAST(:d AS jsonb) WHERE id = :i"),
                    {"i": step_id, "d": json.dumps(detail, ensure_ascii=False, default=str)})
        except Exception as exc2:
            _log_failure("etl_step_journal_failed", exc2, step_id=step_id)

    def _extract(self, run_id: int, window: Window) -> StepResult:
        retries: list[dict[str, Any]] = []
        # I3: `watermark()` endi qayta urinish birligi (`once()`) ICHIDA, extraktsiyadan
        # OLDIN chaqiriladi — konnektor vaqtincha ishlamasa (masalan tarmoq), bu ham qayta
        # uriniladi (avval alohida, himoyalanmagan chaqiruv edi). Faqat OXIRGI (muvaffaqiyatli)
        # urinishning watermark'i ishlatiladi — `once()` faqat ikkalasi (watermark + extract)
        # muvaffaqiyatli bo'lgandagina normal qaytadi.
        captured: list[Watermark] = []

        def once() -> ExtractStats:
            health = self.connector.healthcheck()
            if not health.ok:
                raise ConnectorUnavailableError(health.detail or "источник недоступен")
            captured.append(self.connector.watermark())
            if getattr(self.connector, "buffered", False):
                # M9: tashqi manbani kutish paytida DB tranzaksiyasi ochiq turmasin
                # (idle_in_transaction timeout) — avval xotiraga, keyin qisqa tranzaksiyada.
                buffer = _BufferSink()
                stats = self.connector.extract(window, buffer)
                with etl_transaction() as conn:
                    clear_load(conn, run_id)
                    sink = DbStagingSink(conn, run_id, self.connector.source)
                    for target, row in buffer.rows:
                        sink.add(target, row)
                    sink.close()
                return stats
            with etl_transaction() as conn:
                clear_load(conn, run_id)
                sink = DbStagingSink(conn, run_id, self.connector.source)
                stats = self.connector.extract(window, sink)
                sink.close()
            return stats

        def on_retry(attempt: int, exc: BaseException, pause: float) -> None:
            retries.append({"attempt": attempt, "error": safe_error(exc), "pause": round(pause, 1)})
            log.warning("etl_retry", run_id=run_id, attempt=attempt, pause=round(pause, 1),
                       error_class=type(exc).__name__, sqlstate=sqlstate_of(exc))

        try:
            stats = call_with_retries(once, delays=self.delays, sleep=self.sleep,
                                      jitter=self.jitter, rng=self.rng, on_retry=on_retry)
        except Exception as exc:
            # M10: give-up holatida ham qayta urinishlar jurnali (`retries`) etl_step.detail'da
            # saqlanishi kerak — `_step()`ning umumiy {"error": ...} shakllantirishi buni
            # yo'qotmasin deb shu yerda tafsilotga biriktirilgan holda qayta ko'tariladi.
            raise _StepDetailError(exc, {"retries": retries}) from exc
        return StepResult(stats.rows, {"by_target": dict(stats.by_target), "retries": retries},
                          (stats, captured[-1]))

    def _dims(self, run_id: int) -> StepResult:
        with etl_transaction() as conn:
            return _merge_result(merge_dims(conn, load_id=run_id, source=self.connector.source,
                                            as_of=self.today))

    def _facts(self, run_id: int, window: Window, complete: Any) -> StepResult:
        with etl_transaction() as conn:
            return _merge_result(merge_facts(conn, load_id=run_id, source=self.connector.source,
                                             window=window, complete=set(complete),
                                             as_of=self.today))

    def _aggregates(self, run_id: int, params: BuildParams) -> StepResult:
        with etl_transaction() as conn:
            build_id = builds.create_build(conn, run_id)
            counts = build_all(conn, build_id, params)
            builds.mark_ready(conn, build_id)
        return StepResult(sum(counts.values()), {"build_id": build_id, **counts}, build_id)

    def _quality(self, run_id: int, build_id: int, window: Window) -> StepResult:
        totals = self.connector.control_totals(window)
        try:
            with etl_transaction() as conn:
                results = run_checks(conn, run_id=run_id, build_id=build_id,
                                     source=self.connector.source, window=window, totals=totals)
        except (RuntimeError, ValueError) as exc:
            # I1: `run_checks()`ning KONTEKST tekshiruvi (scope_all / build egaligi) — bu
            # dasturiy xato, xabari faqat ID/kod (quality.py, task-7 fix r1 M2/M3) — xavfsiz,
            # shuning uchun bizning yopiq (xavfsiz) turimizga o'rab beriladi.
            raise QualityContextError(str(exc)) from exc
        bad = failed(results)
        detail = {r.code: {"ok": r.ok, **r.detail} for r in results}
        return StepResult(len(bad), detail, bad, ok=not bad)

    def _publish(self, run_id: int, build_id: int, keep: int) -> StepResult:
        with etl_transaction() as conn:
            builds.publish(conn, build_id, keep=keep)
            conn.execute(text("DELETE FROM stg.rows WHERE load_id = :l"), {"l": run_id})
        return StepResult(0, {"build_id": build_id})

    # -- Yakunlash -----------------------------------------------------
    def _fail_quality(self, run_id: int, build_id: int, bad: list[CheckResult], rows_in: int,
                      rows_upserted: int, merge_stats: list[MergeStats],
                      started_audit_ok: bool) -> RunResult:
        self._safe_mark_failed(build_id)
        codes = ", ".join(r.code for r in bad)
        error = f"Проверки качества не пройдены: {codes}"
        source = self.connector.source
        # I2: xabarnomalar birinchi (himoyalangan), keyin jurnal.
        self._notify(Notification(
            "etl_quality", f"Загрузка «{source}» не опубликована: проверки качества",
            f"Запуск №{run_id}. {error}.\n"
            + json.dumps({r.code: r.detail for r in bad}, ensure_ascii=False, default=str)[:3000]))
        if any(r.code == "control_totals" for r in bad):
            self._notify(Notification(
                "control_totals", f"Расхождение контрольных сумм с источником «{source}»",
                f"Запуск №{run_id}: отклонение от оборотов 1С более 0,1%."))
        self._notify_row_errors(run_id, merge_stats, published=False)
        journal_ok = self._finish_safely(run_id, "failed_quality", build_id, rows_in,
                                         rows_upserted, None, error)
        return RunResult(run_id, "failed_quality", build_id, error,
                         journal_failed=not (started_audit_ok and journal_ok))

    def _notify_row_errors(self, run_id: int, stats: list[MergeStats], *, published: bool) -> None:
        """Controller ruling: bloklovchi bo'lmagan kod bilan rad etilgan qatorlar (masalan
        `negative_amount`, `missing_value`) bo'lsa ham — run muvaffaqiyatli tugashi mumkin
        (quality.py faqat `missing_branch`/`missing_dim`ni tekshiradi). Shunga qaramay bu
        ko'rinmas qolmasligi kerak: xabarnomada FAQAT maqsad nomi va son (xato/ogohlantirish
        soni) — hech qanday xom qiymat, INN, hisob raqami, bank kodi yoki kontragent nomi yo'q.
        M6: xato/ogohlantirish sonlari ALOHIDA qatorlarda, nashr holati aniq aytiladi."""
        total_errors = sum(s.errors for s in stats)
        if total_errors <= 0:
            return
        total_warnings = sum(s.warnings for s in stats)
        lines = "\n".join(
            f"  {s.target}: ошибок {s.errors}, предупреждений {s.warnings}"
            for s in stats if s.errors or s.warnings
        )
        status_line = ("Публикация выполнена." if published
                       else "Публикация заблокирована (проверки качества не пройдены).")
        source = self.connector.source
        self._notify(Notification(
            "etl_row_errors", f"Загрузка «{source}»: часть строк отклонена при слиянии",
            f"Запуск №{run_id}. {status_line}\n"
            f"Отклонено строк (ошибки): {total_errors}\n"
            f"Предупреждения: {total_warnings}\n"
            f"Подробности — в core.etl_error (только счётчики по цели, без значений полей):\n"
            f"{lines}"))

    def _notify(self, notification: Notification) -> None:
        # M7: har bir xabarnoma chaqiruvi himoyalangan — bitta kanal (masalan SMTP)
        # yiqilishi pipeline natijasini yoki boshqa xabarnomalarni to'xtatmasligi kerak.
        try:
            self.notifier.notify(notification)
        except Exception as exc:
            _log_failure("etl_notify_failed", exc, kind=notification.kind)

    def _safe_mark_failed(self, build_id: int) -> None:
        try:
            with etl_transaction() as conn:
                builds.mark_failed(conn, build_id)
        except Exception as exc:
            _log_failure("build_mark_failed_error", exc, build_id=build_id)

    def _finish_safely(self, run_id: int, status: str, build_id: int | None, rows_in: int,
                       rows_upserted: int, watermark: datetime | None,
                       error: str | None) -> bool:
        # I2: `_finish()`ning o'zi hech qachon ko'tarmaydi (ikkala ichki qadami alohida
        # himoyalangan), lekin bu yerda YANA bir himoya qatlami — agar u qandaydir sababdan
        # (masalan monkeypatch/kutilmagan bug) baribir ko'tarsa ham, `run()` HECH QACHON
        # ko'tarmasligi kerak.
        try:
            return self._finish(run_id, status, build_id, rows_in, rows_upserted, watermark,
                               error)
        except Exception as exc:
            _log_failure("etl_finish_failed", exc, run_id=run_id)
            return False

    def _finish(self, run_id: int, status: str, build_id: int | None, rows_in: int,
               rows_upserted: int, watermark: datetime | None, error: str | None) -> bool:
        journal_ok = True
        try:
            with etl_transaction() as conn:
                conn.execute(text(
                    "UPDATE core.etl_run SET status = :st, finished_at = now(), build_id = :b, "
                    "rows_in = :ri, rows_upserted = :ru, watermark = :w, error = :e "
                    "WHERE id = :r"),
                    {"st": status, "b": build_id, "ri": rows_in, "ru": rows_upserted,
                     "w": watermark, "e": error, "r": run_id})
        except Exception as exc:
            journal_ok = False
            _log_failure("etl_run_finish_failed", exc, run_id=run_id)
        audit_ok = self._audit(AuditAction.ETL_RUN_FINISHED, run_id,
                               "ok" if status == "success" else "fail",
                               {"source": self.connector.source, "status": status,
                                "build_id": build_id, "rows_upserted": rows_upserted})
        return journal_ok and audit_ok

    def _audit(self, action: AuditAction, run_id: int, result: AuditResult,
              details: dict[str, Any]) -> bool:
        # I2: audit yozuvi (hash-zanjir) muvaffaqiyatsiz bo'lishi mumkin (masalan DB band) —
        # bu HECH QACHON ETL pipeline natijasini (yoki `run()`ning o'zini) yiqitmasligi kerak.
        try:
            record(AuditEvent(action=action, result=result, user_id=self.triggered_by,
                              object_type="etl_run", object_id=str(run_id), details=details),
                  role="etl")
            return True
        except Exception as exc:
            _log_failure("etl_audit_failed", exc, run_id=run_id, action=str(action))
            return False
