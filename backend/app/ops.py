"""Ekspluatatsiya tekshiruvlari (docs/ops/monitoring.md) va tiklash testi natijasi (spec 11, TZ 9).

`ops_check()` DB darajasidagi holatni faqat o'qiydi: audit default partitsiyasi, keyingi oy audit
partitsiyasi, ma'lumot yangiligi, oylik tiklash testi, faol DEK yoshi, ilova va DB soatlari farqi
(`core.audit_append` ±5 daqiqa oynasi va TOTP uchun NTP shart), WAL arxivatori (RPO), navbatda
qotib qolgan ETL so'rovlari, ixtiyoriy — TLS sertifikat muddati.
Yagona yozuvchi — `record_restore_test`: `core.settings` dagi `last_restore_test` tizim yozuvi.
Bu kalit `DEFAULT_SETTINGS` da yo'q — admin API uni ko'rsatmaydi va tahrirlay olmaydi (404).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from cryptography import x509
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.db import get_engine
from app.dwh.freshness import freshness

RESTORE_KEY = "last_restore_test"
RESTORE_MAX_AGE = timedelta(days=35)
RTO_SECONDS = 7200
RPO = timedelta(minutes=15)  # 04b: core.settings'ga ko'chirilishi mumkin
DEK_MAX_AGE = timedelta(days=365)
CLOCK_SKEW_MAX = timedelta(seconds=60)
ETL_REQUEST_STUCK = timedelta(minutes=30)
TLS_WARN = timedelta(days=30)
TLS_CRITICAL = timedelta(days=7)

Level = Literal["warning", "critical"]
RestoreStatus = Literal["ok", "fail"]
ArchiverStatus = Literal["ok", "skipped", "alarm"]


@dataclass(frozen=True, slots=True)
class Problem:
    code: str
    level: Level
    message: str


@dataclass(frozen=True, slots=True)
class RestoreResult:
    at: datetime
    result: RestoreStatus
    duration_seconds: int
    backup: str
    details: str

    @property
    def rto_ok(self) -> bool:
        return self.duration_seconds <= RTO_SECONDS


def _utcnow() -> datetime:
    return datetime.now(UTC)


def record_restore_test(conn: Connection, result: RestoreResult) -> int:
    """Yangi versiya qatori (oldingisi is_current = false). Versiya raqamini qaytaradi."""
    value = {
        "at": result.at.astimezone(UTC).isoformat(),
        "result": result.result,
        "duration_seconds": result.duration_seconds,
        "rto_ok": result.rto_ok,
        "backup": result.backup[:64],
        "details": result.details[:2000],
    }
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('ugk_restore_test'))"))
    version = int(
        conn.execute(
            text("SELECT coalesce(max(version), 0) + 1 FROM core.settings WHERE key = :k"),
            {"k": RESTORE_KEY},
        ).scalar_one()
    )
    conn.execute(
        text("UPDATE core.settings SET is_current = false WHERE key = :k AND is_current"),
        {"k": RESTORE_KEY},
    )
    conn.execute(
        text(
            "INSERT INTO core.settings (key, version, value) "
            "VALUES (:k, :v, CAST(:val AS jsonb))"
        ),
        {"k": RESTORE_KEY, "v": version, "val": json.dumps(value, ensure_ascii=False)},
    )
    return version


def last_restore_test(conn: Connection) -> dict[str, Any] | None:
    value = conn.execute(
        text("SELECT value FROM core.settings WHERE key = :k AND is_current"), {"k": RESTORE_KEY}
    ).scalar_one_or_none()
    return None if value is None else dict(value)


def check_restore(value: dict[str, Any] | None, now: datetime) -> list[Problem]:
    if value is None:
        return [Problem("restore_test_missing", "warning",
                        "Тест восстановления из резервной копии ещё не проводился")]
    at = datetime.fromisoformat(str(value["at"]))
    problems: list[Problem] = []
    if value.get("result") != "ok":
        problems.append(Problem("restore_test_failed", "critical",
                                f"Тест восстановления {at:%d.%m.%Y} завершился ошибкой"))
    elif not value.get("rto_ok", False):
        problems.append(Problem(
            "restore_test_rto", "warning",
            f"Восстановление заняло {value.get('duration_seconds')} с — "
            f"больше RTO {RTO_SECONDS} с"))
    if now - at > RESTORE_MAX_AGE:
        problems.append(Problem(
            "restore_test_overdue", "warning",
            f"Тест восстановления не проводился с {at:%d.%m.%Y} (норма — ежемесячно)"))
    return problems


def check_tls(path: Path, now: datetime) -> list[Problem]:
    cert = x509.load_pem_x509_certificate(path.read_bytes())
    expires = cert.not_valid_after_utc
    left = expires - now
    message = f"TLS-сертификат истекает {expires:%d.%m.%Y}"
    if left <= TLS_CRITICAL:
        return [Problem("tls_cert_expiring", "critical", message)]
    if left <= TLS_WARN:
        return [Problem("tls_cert_expiring", "warning", message)]
    return []


def check_archiver(
    archive_mode: str,
    last_archived: datetime | None,
    last_failed: datetime | None,
    started: datetime,
    now: datetime,
) -> tuple[ArchiverStatus, list[Problem]]:
    """WAL arxivatori (RPO). `failed_count` ga qarab signal BERILMAYDI: stanza-create'dan oldingi
    boshlang'ich xatolar kutilgan va qayta uriniladi — faqat OXIRGI urinish xato bo'lsa."""
    if archive_mode == "off":
        return "skipped", []
    if last_failed is not None and (last_archived is None or last_failed > last_archived):
        return "alarm", [Problem("wal_archiver_failed", "critical",
                                 "Последняя попытка архивации WAL завершилась ошибкой")]
    # Сервер, работающий меньше RPO, ещё не мог успеть заархивировать сегмент.
    if now - started > RPO and (last_archived is None or now - last_archived > RPO):
        return "alarm", [Problem("wal_archiver_lag", "critical",
                                 "WAL не архивировался дольше 15 минут — RPO под угрозой")]
    return "ok", []


def _next_month(now: datetime) -> str:
    first = now.astimezone(UTC).replace(day=1)
    return (first + timedelta(days=32)).strftime("%Y%m")


def ops_check(
    now: datetime | None = None,
    tls_cert: Path | None = None,
    app_clock: Callable[[], datetime] = _utcnow,
    notes: list[str] | None = None,
) -> list[Problem]:
    """`notes` (ixtiyoriy) — muammo bo'lmagan ma'lumot qatorlari (masalan, `skipped` qoidalar)."""
    now = now or _utcnow()
    problems: list[Problem] = []
    with get_engine("app").connect() as conn:
        default_rows = int(conn.execute(text(
            "SELECT count(*) FROM core.audit_log "
            "WHERE tableoid = 'core.audit_log_default'::regclass"
        )).scalar_one())
        if default_rows:
            problems.append(Problem(
                "audit_default_rows", "warning",
                f"В партиции core.audit_log_default {default_rows} записей — "
                "проверьте обслуживание партиций (worker, задача partitions)"))
        partition = f"core.audit_log_{_next_month(now)}"
        if conn.execute(text("SELECT to_regclass(:n)"), {"n": partition}).scalar() is None:
            problems.append(Problem("audit_partition_missing", "critical",
                                    f"Нет партиции {partition} — записи аудита попадут в default"))
        state = freshness(conn, now)
        if state.stale:
            problems.append(Problem("stale_data", "warning",
                                    f"Данные витрины не обновлялись более {state.max_age_hours} ч"))
        stuck = int(conn.execute(text(
            "SELECT count(*) FROM core.etl_requests "
            "WHERE status = 'pending' AND requested_at < :t"
        ), {"t": now - ETL_REQUEST_STUCK}).scalar_one())
        if stuck:
            problems.append(Problem("etl_request_stuck", "warning",
                                    f"Запросов загрузки в очереди дольше 30 минут: {stuck}"))
        problems.extend(check_restore(last_restore_test(conn), now))
        rows = conn.execute(text(
            "SELECT purpose, created_at FROM core.crypto_keys "
            "WHERE status = 'active' ORDER BY purpose"))
        for purpose, created_at in rows:
            if now - created_at > DEK_MAX_AGE:
                problems.append(Problem("key_rotation_due", "warning",
                                        f"Ключ {purpose}: активная версия старше 365 дней"))
        mode, archived, failed, started = conn.execute(text(
            "SELECT current_setting('archive_mode'), a.last_archived_time, a.last_failed_time, "
            "pg_postmaster_start_time() FROM pg_stat_archiver a"
        )).one()
        status, found = check_archiver(mode, archived, failed, started, now)
        problems.extend(found)
        if status == "skipped" and notes is not None:
            notes.append("wal_archiver: skipped (archive_mode=off)")
        db_now: datetime = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
    skew = abs(db_now - app_clock())
    if skew > CLOCK_SKEW_MAX:
        problems.append(Problem(
            "clock_skew", "critical",
            f"Часы приложения и СУБД расходятся на {int(skew.total_seconds())} с — "
            "проверьте chrony/NTP"))
    if tls_cert is not None:
        problems.extend(check_tls(tls_cert, now))
    return problems


def report(problems: list[Problem]) -> str:
    if not problems:
        return "ops-check: замечаний нет"
    return "\n".join(f"[{p.level.upper()}] {p.code}: {p.message}" for p in problems)
