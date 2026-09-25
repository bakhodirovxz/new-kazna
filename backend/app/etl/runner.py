"""ETL runner (spec 5.1): PostgreSQL advisory lock bilan bitta vaqtda bitta yuklash.

Pipeline: extract -> dims -> facts -> aggregates -> quality -> publish. Istalgan qadam xatosi
yoki sifat buzilishi -> publish yo'q, oldingi build aktiv qoladi, notifier chaqiriladi.
Har qadam core.etl_step ga, yuklash core.etl_run ga, boshlanish/tugash auditga yoziladi.

Task-8 amendments (A8.1/A8.2): `AuditEvent.result` — `Literal["ok","fail","denied"]`
(app/audit/service.py) — `_audit()` shu turdagi parametr oladi (mypy strict); `record()`
`role="etl"` bilan chaqiriladi — worker `ugk_etl` ulanishi orqali audit yozadi (carry note:
ugk_etl'ning `audit_reserve`/`audit_append`ga EXECUTE huquqi bor, 0004_audit.py).

Controller ruling (task-8, extra requirement): `app/etl/merge.py` bloklovchi bo'lmagan kod bilan
(masalan `negative_amount`, `missing_value`) rad etgan qatorlar sifat tekshiruvini to'xtatmaydi
(`app/etl/quality.py` faqat `missing_branch`/`missing_dim`ni bloklaydi) — ular baribir ko'rinishi
kerak: (1) har maqsad bo'yicha xato/ogohlantirish soni `core.etl_step.detail`da (`_merge_result`
orqali, allaqachon mavjud), (2) agar jami xato > 0 bo'lsa — xabarnomada, FAQAT sonlar bilan
(xom qiymat, INN, hisob raqami, bank kodi, kontragent nomi yoki `*_enc` HECH QACHON yozilmaydi).
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable, Sequence
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

ETL_LOCK = "ugk_etl"
INCREMENTAL_LOOKBACK = timedelta(days=45)
AGGREGATE_YEARS = 10  # spec 4.7: agregatlar 10 yil saqlanadi
log = get_logger("ugekazna.etl")


class EtlBusyError(Exception):
    """Boshqa yuklash bajarilmoqda."""


@dataclass(frozen=True, slots=True)
class RunResult:
    run_id: int | None
    status: str
    build_id: int | None = None
    error: str | None = None


@dataclass
class StepResult:
    rows: int = 0
    detail: dict[str, Any] = field(default_factory=dict)
    value: Any = None
    ok: bool = True


def compute_window(mode: Mode, *, today: date, history_start: date,
                   last_watermark: datetime | None) -> Window:
    """To'liq: tarix boshidan. Inkremental: min(watermark - 45 kun, joriy oy boshi) -- TZ:
    "последние 45 дней плюс текущий месяц целиком"; eski watermark oraliqni ham qamraydi."""
    if mode == Mode.FULL or last_watermark is None:
        return Window(history_start, today)
    wm_day = last_watermark.astimezone(TASHKENT).date()
    start = min(wm_day - INCREMENTAL_LOOKBACK, month_start(today))
    return Window(max(start, history_start), today)


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:400]}"


def _merge_result(stats: list[MergeStats]) -> StepResult:
    detail = {
        s.target: {"upserted": s.upserted, "deleted": s.deleted, "errors": s.errors,
                   "warnings": s.warnings}
        for s in stats
    }
    return StepResult(sum(s.upserted for s in stats), detail, stats)


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
                lock.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": ETL_LOCK})

    # -- Pipeline ----------------------------------------------------------
    def _run_locked(self) -> RunResult:
        source = self.connector.source
        with etl_transaction() as conn:
            # Lock bizda -- "running" holatidagi har qanday yugurish o'lik (worker to'xtagan).
            conn.execute(text(
                "UPDATE core.etl_run SET status = 'failed', finished_at = now(), "
                "error = 'Прервано: процесс загрузки был остановлен' WHERE status = 'running'"))
            history_start = date.fromisoformat(str(current_setting(conn, "etl.history_start")))
            keep = int(current_setting(conn, "builds.keep"))
            fact_years = int(current_setting(conn, "retention.fact_years"))
            last = conn.execute(text(
                "SELECT watermark FROM core.etl_run WHERE source = :s AND status = 'success' "
                "AND watermark IS NOT NULL ORDER BY id DESC LIMIT 1"), {"s": source}).scalar()
            window = compute_window(self.mode, today=self.today, history_start=history_start,
                                    last_watermark=last)
            run_id = int(conn.execute(text(
                "INSERT INTO core.etl_run (source, mode, status, window_from, window_to, "
                "triggered_by) VALUES (:s, :m, 'running', :f, :t, :u) RETURNING id"),
                {"s": source, "m": self.mode.value, "f": window.date_from, "t": window.date_to,
                 "u": self.triggered_by}).scalar_one())
        self._audit(AuditAction.ETL_RUN_STARTED, run_id, "ok",
                    {"source": source, "mode": self.mode.value,
                     "window": [window.date_from.isoformat(), window.date_to.isoformat()]})

        build_id: int | None = None
        rows_in = rows_upserted = 0
        try:
            watermark: Watermark = self.connector.watermark()
            extract = self._step(run_id, "extract", lambda: self._extract(run_id, window))
            stats: ExtractStats = extract.value
            rows_in = stats.rows
            dims = self._step(run_id, "dims", lambda: self._dims(run_id))
            facts = self._step(run_id, "facts",
                               lambda: self._facts(run_id, window, stats.by_target.keys()))
            rows_upserted = dims.rows + facts.rows
            # Controller ruling: bloklovchi bo'lmagan rad etilgan qatorlar (agar bo'lsa) —
            # run muvaffaqiyatli/muvaffaqiyatsiz bo'lishidan qat'i nazar, darhol ko'rinadi.
            self._notify_row_errors(run_id, [*dims.value, *facts.value])
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
                return self._fail_quality(run_id, build_id, bad, rows_in, rows_upserted)
            self._step(run_id, "publish", lambda: self._publish(run_id, int(aggregates.value),
                                                                keep))
        except Exception as exc:  # yuklash xatosi jurnalga yoziladi, qayta ko'tarilmaydi
            log.error("etl_failed", run_id=run_id, source=source, error=type(exc).__name__,
                      exc_info=exc)
            if build_id is not None:
                self._safe_mark_failed(build_id)
            error = _describe(exc)
            self._finish(run_id, "failed", build_id, rows_in, rows_upserted, None, error)
            self.notifier.notify(Notification(
                "etl_failed", f"Загрузка «{source}» завершилась ошибкой",
                f"Запуск №{run_id}, режим {self.mode.value}.\nОшибка: {error}"))
            return RunResult(run_id, "failed", build_id, error)
        self._finish(run_id, "success", build_id, rows_in, rows_upserted, watermark.value, None)
        return RunResult(run_id, "success", build_id)

    def _step(self, run_id: int, name: str, fn: Callable[[], StepResult]) -> StepResult:
        with etl_transaction() as conn:
            step_id = conn.execute(text(
                "INSERT INTO core.etl_step (run_id, name, status) VALUES (:r, :n, 'running') "
                "RETURNING id"), {"r": run_id, "n": name}).scalar_one()
        try:
            result = fn()
        except Exception as exc:
            with etl_transaction() as conn:
                conn.execute(text(
                    "UPDATE core.etl_step SET status = 'failed', finished_at = now(), "
                    "detail = CAST(:d AS jsonb) WHERE id = :i"),
                    {"i": step_id, "d": json.dumps({"error": _describe(exc)}, ensure_ascii=False)})
            raise
        with etl_transaction() as conn:
            conn.execute(text(
                "UPDATE core.etl_step SET status = :st, finished_at = now(), rows = :n, "
                "detail = CAST(:d AS jsonb) WHERE id = :i"),
                {"i": step_id, "st": "success" if result.ok else "failed", "n": result.rows,
                 "d": json.dumps(result.detail, ensure_ascii=False, default=str)})
        return result

    def _extract(self, run_id: int, window: Window) -> StepResult:
        retries: list[dict[str, Any]] = []

        def once() -> ExtractStats:
            health = self.connector.healthcheck()
            if not health.ok:
                raise ConnectorUnavailableError(health.detail or "источник недоступен")
            with etl_transaction() as conn:
                clear_load(conn, run_id)
                sink = DbStagingSink(conn, run_id, self.connector.source)
                stats = self.connector.extract(window, sink)
                sink.close()
            return stats

        def on_retry(attempt: int, exc: BaseException, pause: float) -> None:
            retries.append({"attempt": attempt, "error": _describe(exc), "pause": round(pause, 1)})
            log.warning("etl_retry", run_id=run_id, attempt=attempt, pause=round(pause, 1),
                        error=type(exc).__name__)

        stats = call_with_retries(once, delays=self.delays, sleep=self.sleep, jitter=self.jitter,
                                  rng=self.rng, on_retry=on_retry)
        return StepResult(stats.rows, {"by_target": dict(stats.by_target), "retries": retries},
                          stats)

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
        with etl_transaction() as conn:
            results = run_checks(conn, run_id=run_id, build_id=build_id,
                                 source=self.connector.source, window=window, totals=totals)
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
                      rows_upserted: int) -> RunResult:
        self._safe_mark_failed(build_id)
        codes = ", ".join(r.code for r in bad)
        error = f"Проверки качества не пройдены: {codes}"
        self._finish(run_id, "failed_quality", build_id, rows_in, rows_upserted, None, error)
        source = self.connector.source
        self.notifier.notify(Notification(
            "etl_quality", f"Загрузка «{source}» не опубликована: проверки качества",
            f"Запуск №{run_id}. {error}.\n"
            + json.dumps({r.code: r.detail for r in bad}, ensure_ascii=False, default=str)[:3000]))
        if any(r.code == "control_totals" for r in bad):
            self.notifier.notify(Notification(
                "control_totals", f"Расхождение контрольных сумм с источником «{source}»",
                f"Запуск №{run_id}: отклонение от оборотов 1С более 0,1%."))
        return RunResult(run_id, "failed_quality", build_id, error)

    def _notify_row_errors(self, run_id: int, stats: list[MergeStats]) -> None:
        """Controller ruling: bloklovchi bo'lmagan kod bilan rad etilgan qatorlar (masalan
        `negative_amount`, `missing_value`) bo'lsa ham — run muvaffaqiyatli tugashi mumkin
        (quality.py faqat `missing_branch`/`missing_dim`ni tekshiradi). Shunga qaramay bu
        ko'rinmas qolmasligi kerak: xabarnomada FAQAT maqsad nomi va son (xato/ogohlantirish
        soni) — hech qanday xom qiymat, INN, hisob raqami, bank kodi yoki kontragent nomi yo'q
        (bular umuman shu yerga uzatilmaydi, faqat `MergeStats` sonlari)."""
        total_errors = sum(s.errors for s in stats)
        if total_errors <= 0:
            return
        total_warnings = sum(s.warnings for s in stats)
        lines = "\n".join(
            f"  {s.target}: ошибок {s.errors}, предупреждений {s.warnings}"
            for s in stats if s.errors or s.warnings
        )
        source = self.connector.source
        self.notifier.notify(Notification(
            "etl_row_errors", f"Загрузка «{source}»: часть строк отклонена при слиянии",
            f"Запуск №{run_id}. Отклонено строк (не блокирует публикацию): {total_errors} "
            f"с ошибкой, {total_warnings} с предупреждением. Подробности — в core.etl_error "
            f"(только счётчики по цели, без значений полей):\n{lines}"))

    def _safe_mark_failed(self, build_id: int) -> None:
        try:
            with etl_transaction() as conn:
                builds.mark_failed(conn, build_id)
        except Exception as exc:
            log.error("build_mark_failed_error", build_id=build_id, error=type(exc).__name__)

    def _finish(self, run_id: int, status: str, build_id: int | None, rows_in: int,
                rows_upserted: int, watermark: datetime | None, error: str | None) -> None:
        with etl_transaction() as conn:
            conn.execute(text(
                "UPDATE core.etl_run SET status = :st, finished_at = now(), build_id = :b, "
                "rows_in = :ri, rows_upserted = :ru, watermark = :w, error = :e WHERE id = :r"),
                {"st": status, "b": build_id, "ri": rows_in, "ru": rows_upserted,
                 "w": watermark, "e": error, "r": run_id})
        self._audit(AuditAction.ETL_RUN_FINISHED, run_id, "ok" if status == "success" else "fail",
                    {"source": self.connector.source, "status": status, "build_id": build_id,
                     "rows_upserted": rows_upserted})

    def _audit(self, action: AuditAction, run_id: int, result: AuditResult,
               details: dict[str, Any]) -> None:
        record(AuditEvent(action=action, result=result, user_id=self.triggered_by,
                          object_type="etl_run", object_id=str(run_id), details=details),
               role="etl")
