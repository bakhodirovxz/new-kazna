"""ETL worker (spec 5.1): APScheduler BlockingScheduler. `python -m app.worker`.

Joblar (Toshkent vaqti): dev'da kechasi to'liq sintetik yuklash (prod'da haqiqiy konnektorlar
keyingi rejalarda), admin navbatidagi so'rovlar (30 s), partitsiyalar (03:30), sessiya/staging
tozalash (04:00), freshness (30 daqiqa), heartbeat. Kalit boshqaruvi (retire/rewrap) bu yerda
YO'Q: worker'da migrator siri yo'q (faqat `migrate` konteyneri).
Har xizmat jobi o'z advisory lock'i ostida; ETL runner'ning o'z global lock'i bor.
Istisnolar faqat `safe_error`/`sqlstate_of` orqali loglanadi (exc_info/str(exc) yo'q — A14.8).
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from app.audit.service import AuditAction, AuditEvent, record
from app.bootstrap import bootstrap_runtime
from app.core import integrations, sysconfig
from app.core.config import ConfigError, Settings, get_settings
from app.core.db import get_engine
from app.core.logging import configure_logging, get_logger
from app.dwh import partitions
from app.dwh.dates import TASHKENT, today_tashkent
from app.dwh.freshness import freshness
from app.etl.connectors import make_connector
from app.etl.db import etl_transaction
from app.etl.errors import FILE_FULL_REFUSED, EtlBusyError, safe_error, sqlstate_of
from app.etl.notify import Notification, Notifier, build_notifier
from app.etl.probes import process_integration_checks
from app.etl.runner import Runner, RunResult
from app.etl.types import Mode, SourceConnector
from app.maintenance import cleanup_sessions, cleanup_staging
from app.reports.daily import send_daily_summary

log = get_logger("ugekazna.worker")
HEARTBEAT = Path("/tmp/worker-heartbeat")  # noqa: S108 — tmpfs, faqat healthcheck  # nosec B108
_NEVER: Any = object()
_alerted_for: Any = _NEVER


def _log_error(event: str, exc: BaseException, **fields: Any) -> None:
    log.error(event, error=safe_error(exc), sqlstate=sqlstate_of(exc), **fields)


@contextmanager
def job_lock(name: str) -> Iterator[bool]:
    key = f"ugk_job:{name}"
    with get_engine("etl").connect() as raw:
        conn = raw.execution_options(isolation_level="AUTOCOMMIT")
        got = bool(conn.execute(text("SELECT pg_try_advisory_lock(hashtext(:k))"),
                                {"k": key}).scalar_one())
        try:
            yield got
        finally:
            if got:
                conn.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": key})


class _ClassOnlyFormatter(logging.Formatter):
    def formatException(self, ei: Any) -> str:  # noqa: N802 — stdlib API
        return str(ei[0].__name__)  # traceback/xabar matni yo'q: faqat sinf nomi


def configure_stdlib_logging() -> None:
    """APScheduler stdlib `logging` ishlatadi va `logger.exception(...)` zanjirli traceback
    (asl istisno matni, SQL parametrlari) chiqarishi mumkin. Shu logger'ga tracebacksiz
    handler qo'yamiz (faqat sinf nomi) va root'ga uzatmaymiz (A14.8)."""
    logger = logging.getLogger("apscheduler")
    for h in list(logger.handlers):
        logger.removeHandler(h)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_ClassOnlyFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _guarded(name: str, fn: Callable[[], object]) -> Callable[[], None]:
    def job() -> None:
        try:
            with job_lock(name) as got:
                if not got:
                    log.info("job_skipped_locked", job=name)
                    return
                fn()
        except Exception as exc:  # job xatosi scheduler'ni to'xtatmasin (traceback yo'q)
            _log_error("job_failed", exc, job=name)

    return job


def run_etl_job(source: str, mode: Mode, notifier: Notifier) -> RunResult | None:
    try:
        if source == "onec":
            with get_engine("etl").connect() as conn:
                if not integrations.configured(conn, "onec"):
                    log.info("etl_skipped_not_configured", source=source)
                    return None
        return Runner(make_connector(source), mode=mode, notifier=notifier).run()
    except EtlBusyError:
        log.info("etl_skipped_busy", source=source)
    except Exception as exc:  # A14.8
        _log_error("etl_job_failed", exc, source=source)
    return None


def notify_bank_errors(run_id: int, notifier: Notifier) -> int:
    """Bank fayllaridagi rad etilgan qator/fayllar haqida bitta xabar (S2 spec 3.2)."""
    with etl_transaction() as conn:
        rows = conn.execute(text(
            "SELECT code, count(*) AS n FROM core.etl_error WHERE run_id = :r "
            "AND step = 'extract' AND target = 'bank_file' GROUP BY code ORDER BY code"),
            {"r": run_id}).all()
    total = sum(int(r.n) for r in rows)
    if total:
        parts = ", ".join(f"{r.code}: {r.n}" for r in rows)
        notifier.notify(Notification(
            "bank_rows_rejected", "Строки банковских выписок отклонены",
            f"Запуск №{run_id}: отклонено {total} ({parts}). "
            "Подробности — «Состояние обменов» или `python -m app.cli bank-files`."))
    return total


def run_banks_job(notifier: Notifier) -> RunResult | None:
    with get_engine("app").connect() as conn:
        accounts = sysconfig.current(conn, "banks.accounts")
    if not accounts or not Path(get_settings().bank_inbox_dir).is_dir():
        log.info("banks_skipped", reason="not_configured")
        return None
    result = run_etl_job("banks", Mode.INCREMENTAL, notifier)
    if result is not None and result.run_id is not None:
        notify_bank_errors(result.run_id, notifier)
    return result


def run_cbu_job(notifier: Notifier) -> RunResult | None:
    with get_engine("app").connect() as conn:
        enabled = bool(sysconfig.current(conn, "cbu.enabled"))
    if not enabled:
        log.info("cbu_skipped", reason="not_configured")
        return None
    return run_etl_job("cbu", Mode.INCREMENTAL, notifier)




def run_hr_job(notifier: Notifier) -> RunResult | None:
    """HR API yuklash (U5: job shartsiz, sozlanmagan bo'lsa o'tkazib yuboriladi); faqat xato
    (warning emas) qatorlar bo'lsa xabar — tashkilot kesimi kelmaguncha kundalik ogohlantirish
    bilan administratorni bezovta qilmaslik uchun. Xabarda faqat kodlar va sonlar."""
    with get_engine("etl").connect() as conn:
        ready = integrations.configured(conn, "hr")
    if not ready:
        log.info("hr_skipped", reason="not_configured")
        return None
    result = run_etl_job("hr", Mode.INCREMENTAL, notifier)
    if result is None or result.run_id is None:
        return result
    with etl_transaction() as conn:
        rows = conn.execute(text(
            "SELECT code, count(*) AS n FROM core.etl_error WHERE run_id = :r "
            "AND target = 'hr_api' AND severity = 'error' GROUP BY code ORDER BY code"),
            {"r": result.run_id}).all()
    if rows:
        lines = "\n".join(f"{r.code}: {r.n}" for r in rows)
        try:
            notifier.notify(Notification(
                "hr_rows_rejected", "Данные HR API отклонены",
                f"Запуск №{result.run_id}. Коды ошибок (значения полей не передаются):\n{lines}\n"
                "Сопоставление организаций — `python -m app.cli hr-orgs`, запрос к разработчикам "
                "HR — docs/integration/hr-sorov-s4.md."))
        except Exception as exc:
            _log_error("hr_notify_failed", exc)
    return result


def _set_request(request_id: int, status: str, run_id: int | None = None,
                 error: str | None = None) -> None:
    with etl_transaction() as conn:
        conn.execute(text("UPDATE core.etl_requests SET status = :s, run_id = :r, error = :e "
                          "WHERE id = :i"),
                     {"s": status, "r": run_id, "e": None if error is None else error[:500],
                      "i": request_id})


def _connector_error(exc: Exception) -> str:
    # Admin kiritgan manba nomi xom matnga kirmasin: qat'iy matnlar.
    if isinstance(exc, ConfigError):
        return "ConfigError: manba bu muhitda taqiqlangan"
    if isinstance(exc, ValueError):
        return "ValueError: noma'lum manba"
    return safe_error(exc)


def recover_stuck_requests() -> int:
    """Worker qayta ishga tushganda `running`da qolib ketgan so'rovlarni yopadi."""
    with etl_transaction() as conn:
        return conn.execute(text(
            "UPDATE core.etl_requests SET status = 'failed', error = :e "
            "WHERE status = 'running'"), {"e": "worker qayta ishga tushdi"}).rowcount


def process_requests(
    notifier: Notifier,
    *,
    factory: Callable[[str], SourceConnector] = make_connector,
    today: date | None = None,
) -> int:
    """Admin navbatidagi so'rovlarni ketma-ket bajaradi; bajarilganlar sonini qaytaradi."""
    done = 0
    while True:
        with etl_transaction() as conn:
            row = conn.execute(text(
                "SELECT id, source, mode, requested_by FROM core.etl_requests "
                "WHERE status = 'pending' ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED")).first()
            if row is None:
                return done
            conn.execute(text("UPDATE core.etl_requests SET status = 'running' WHERE id = :i"),
                         {"i": row.id})
        if row.source == "file" and row.mode == "full":  # I2: CSV to'liq bo'lmasa qatorlar o'chadi
            _set_request(row.id, "failed", error=FILE_FULL_REFUSED)
            done += 1
            continue
        try:
            connector = factory(row.source)
        except Exception as exc:
            _set_request(row.id, "failed", error=_connector_error(exc))
            done += 1
            continue
        try:
            result = Runner(connector, mode=Mode(row.mode), notifier=notifier,
                            triggered_by=row.requested_by, today=today).run()
        except EtlBusyError:
            _set_request(row.id, "pending")  # keyingi tekshiruvda qayta urinamiz
            return done
        except Exception as exc:
            _log_error("etl_request_failed", exc, request_id=row.id)
            _set_request(row.id, "failed", error=safe_error(exc))
            done += 1
            continue
        _set_request(row.id, "done" if result.status == "success" else "failed",
                     result.run_id, result.error)
        done += 1


def maintain_partitions(today: date) -> dict[str, int]:
    with etl_transaction() as conn:
        months_ahead = int(sysconfig.current(conn, "partitions.months_ahead"))
        keep_years = int(sysconfig.current(conn, "retention.fact_years"))
        audit_months = int(sysconfig.current(conn, "retention.audit_months"))
        created = partitions.ensure_ahead(conn, today, months_ahead)
        dropped = partitions.drop_old(conn, keep_years)
        conn.execute(text("SELECT core.ensure_audit_partitions(3)"))
        audit_dropped = int(conn.execute(text("SELECT core.drop_old_audit_partitions(:m)"),
                                         {"m": audit_months}).scalar_one())
    result = {"created": created, "dropped": dropped, "audit_dropped": audit_dropped}
    log.info("partitions_maintained", **result)
    if dropped or audit_dropped:
        record(AuditEvent(action=AuditAction.PARTITIONS_DROPPED, object_type="partitions",
                          details={**result, "keep_years_setting": keep_years,
                                   "keep_years_effective": max(keep_years, 5),
                                   "audit_months_setting": audit_months,
                                   "audit_months_effective": max(audit_months, 12)}),
               role="etl")
    return result


def cleanup_job() -> None:
    challenges, stale = cleanup_sessions()
    staged = cleanup_staging()
    log.info("cleanup_done", challenges=challenges, sessions=stale, staging=staged)


def check_freshness(notifier: Notifier, now: datetime | None = None) -> bool:
    """>6 soat yangilanmagan bo'lsa xabar; bitta eskirish holati uchun bitta xabar."""
    global _alerted_for
    with get_engine("app").connect() as conn:
        state = freshness(conn, now or datetime.now(UTC))
    if not state.stale:
        _alerted_for = _NEVER
        return False
    if _alerted_for is _NEVER or _alerted_for != state.last_success_at:
        last = "никогда" if state.last_success_at is None else \
            state.last_success_at.astimezone(TASHKENT).strftime("%d.%m.%Y %H:%M")
        notifier.notify(Notification(
            "stale_data", "Данные витрины устарели",
            f"Последняя успешная загрузка: {last}. Порог: {state.max_age_hours} ч."))
        _alerted_for = state.last_success_at
    return True


def heartbeat(path: Path = HEARTBEAT) -> None:
    path.touch()


# job_id -> (sozlama kaliti, qo'llangan cron). S1–S5 cron joblari ham shu orqali qo'shiladi.
_applied: dict[str, tuple[str, str]] = {}


def add_cron_job(scheduler: BaseScheduler, job_id: str, key: str, func: Callable[..., Any], *,
                 args: tuple[Any, ...] = (), **opts: Any) -> None:
    with get_engine("app").connect() as conn:
        cron = str(sysconfig.current(conn, key))
    scheduler.add_job(func, CronTrigger.from_crontab(cron, timezone=TASHKENT), args=args,
                      id=job_id, **opts)
    _applied[job_id] = (key, cron)


def sync_schedules(scheduler: BaseScheduler) -> list[str]:
    """Panelda o'zgargan cron'lar ≤ 60 s ichida qo'llanadi (qayta ishga tushirishsiz)."""
    changed: list[str] = []
    with get_engine("app").connect() as conn:
        for job_id, (key, applied) in list(_applied.items()):
            cron = str(sysconfig.current(conn, key))
            if cron == applied or scheduler.get_job(job_id) is None:
                continue
            scheduler.reschedule_job(job_id, trigger=CronTrigger.from_crontab(cron,
                                                                             timezone=TASHKENT))
            _applied[job_id] = (key, cron)
            changed.append(job_id)
    if changed:
        log.info("schedules_synced", jobs=changed)
    return changed


def build_scheduler(settings: Settings, notifier: Notifier, *,
                    scheduler: BlockingScheduler | None = None) -> BlockingScheduler:
    scheduler = scheduler or BlockingScheduler(timezone=TASHKENT)
    _applied.clear()
    opts: dict[str, Any] = {"max_instances": 1, "coalesce": True, "misfire_grace_time": 3600}
    if settings.env == "dev":
        add_cron_job(scheduler, "etl_synthetic_full", "etl.synthetic_cron", run_etl_job,
                     args=("synthetic", Mode.FULL, notifier), **opts)
    # U5: shartsiz; sozlanmagan bo'lsa run_etl_job o'tkazib yuboradi (panelda sozlash — qayta
    # ishga tushirishsiz). TZ 8: to'liq — tunda (06:00 gacha), inkremental — kunduzi 3 marta.
    add_cron_job(scheduler, "etl_onec_full", "etl.onec_full_cron", run_etl_job,
                 args=("onec", Mode.FULL, notifier), **opts)
    add_cron_job(scheduler, "etl_onec_incremental", "etl.onec_incremental_cron", run_etl_job,
                 args=("onec", Mode.INCREMENTAL, notifier), **opts)
    # TZ 8: banklar kuniga 4 marta, ЦБ kurslari har kuni, Telegram hisoboti 08:30; hammasi
    # shartsiz qo'shiladi, sozlanmagan bo'lsa job tanasi o'tkazib yuboradi (U5).
    add_cron_job(scheduler, "etl_banks", "etl.banks_cron", run_banks_job, args=(notifier,), **opts)
    add_cron_job(scheduler, "etl_cbu", "etl.cbu_cron", run_cbu_job, args=(notifier,), **opts)
    add_cron_job(scheduler, "telegram_summary", "telegram.summary_cron",
                 _guarded("telegram_summary", send_daily_summary), **opts)
    # S4: HR API — kuniga bir marta (U5: shartsiz, ichida configured tekshiruvi)
    add_cron_job(scheduler, "etl_hr", "etl.hr_cron", run_hr_job, args=(notifier,), **opts)
    scheduler.add_job(_guarded("etl_requests", lambda: process_requests(notifier)),
                      "interval", seconds=30, id="etl_requests", **opts)
    scheduler.add_job(_guarded("integration_checks", process_integration_checks),
                      "interval", seconds=10, id="integration_checks", **opts)
    add_cron_job(scheduler, "partitions", "maintenance.partitions_cron",
                 _guarded("partitions", lambda: maintain_partitions(today_tashkent())), **opts)
    add_cron_job(scheduler, "cleanup", "maintenance.cleanup_cron",
                 _guarded("cleanup", cleanup_job), **opts)
    scheduler.add_job(_guarded("schedules", lambda: sync_schedules(scheduler)),
                      "interval", seconds=60, id="schedules", **opts)
    scheduler.add_job(_guarded("freshness", lambda: check_freshness(notifier)),
                      "interval", minutes=30, id="freshness", **opts)
    scheduler.add_job(heartbeat, "interval", seconds=60, id="heartbeat", **opts)
    return scheduler


def main() -> None:
    configure_logging()
    configure_stdlib_logging()
    settings = get_settings()
    problems = settings.problems()
    if problems:
        raise ConfigError("; ".join(problems))
    bootstrap_runtime()
    heartbeat()
    log.info("stuck_requests_closed", count=recover_stuck_requests())
    scheduler = build_scheduler(settings, build_notifier())
    log.info("worker_started", env=settings.env, jobs=sorted(j.id for j in scheduler.get_jobs()))
    scheduler.start()


if __name__ == "__main__":
    main()
