"""Ekspluatatsiya tekshiruvlari (docs/ops/monitoring.md) va tiklash testi natijasi (spec 11, TZ 9).

`ops_check()` DB darajasidagi holatni faqat o'qiydi: audit default partitsiyasi, keyingi oy audit
partitsiyasi, ma'lumot yangiligi, oylik tiklash testi, faol DEK yoshi, ilova va DB soatlari farqi
(`core.audit_append` ±5 daqiqa oynasi va TOTP uchun NTP shart), WAL arxivatori (RPO), navbatda
qotib qolgan ETL so'rovlari, prod'da qolgan `load_*` yuklama hisoblari, ixtiyoriy — TLS sertifikat
muddati.
Yagona yozuvchi — `record_restore_test`: `core.settings` dagi `last_restore_test` tizim yozuvi.
Bu kalit sysconfig `REGISTRY` da yo'q — admin API uni ko'rsatmaydi va tahrirlay olmaydi (404).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from cryptography import x509
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core import sysconfig
from app.core.config import get_settings
from app.core.db import get_engine
from app.devtools import LOAD_PREFIX
from app.dwh.freshness import freshness

RESTORE_KEY = "last_restore_test"
# Таймер — первая суббота месяца (интервал до 35 дней) плюс длительность запуска.
RESTORE_MAX_AGE = timedelta(days=40)
RTO_SECONDS = 7200
RPO = timedelta(minutes=15)  # 04b: core.settings'ga ko'chirilishi mumkin
ARCHIVER_GRACE = timedelta(minutes=5)  # archive_timeout + archive-push davomiyligi uchun zaxira
DEK_MAX_AGE = timedelta(days=365)
CLOCK_SKEW_MAX = timedelta(seconds=60)
ETL_REQUEST_STUCK = timedelta(minutes=30)
ETL_RUNNING_STUCK = timedelta(hours=6)
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


def check_restore(value: dict[str, Any] | None, now: datetime, *,
                  max_age: timedelta = RESTORE_MAX_AGE) -> list[Problem]:
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
    if now - at > max_age:
        problems.append(Problem(
            "restore_test_overdue", "warning",
            f"Тест восстановления не проводился с {at:%d.%m.%Y} (норма — ежемесячно)"))
    return problems


def check_tls(path: Path, now: datetime, *, warn: timedelta = TLS_WARN,
              critical: timedelta = TLS_CRITICAL) -> list[Problem]:
    cert = x509.load_pem_x509_certificate(path.read_bytes())
    expires = cert.not_valid_after_utc
    left = expires - now
    message = f"TLS-сертификат истекает {expires:%d.%m.%Y}"
    if left <= critical:
        return [Problem("tls_cert_expiring", "critical", message)]
    if left <= warn:
        return [Problem("tls_cert_expiring", "warning", message)]
    return []


@dataclass(frozen=True, slots=True)
class ArchiverState:
    archive_mode: str
    archive_timeout: timedelta
    last_archived_wal: str | None
    last_archived: datetime | None
    last_failed: datetime | None
    current_wal: str | None  # None — replika (pg_current_wal_lsn mavjud emas)
    segment_bytes: int
    started: datetime
    now: datetime  # DB soati


WAL_NAME_RE = re.compile(r"[0-9A-F]{24}")


def _segno(wal: str, segment_bytes: int) -> tuple[int, int]:
    """WAL fayl nomi (24 hex) -> (timeline, mutlaq segment raqami)."""
    per_log = 0x100000000 // segment_bytes
    return int(wal[:8], 16), int(wal[8:16], 16) * per_log + int(wal[16:24], 16)


def check_archiver(st: ArchiverState) -> tuple[ArchiverStatus, list[Problem], list[str]]:
    """WAL arxivatori (RPO). `failed_count` ga qarab signal BERILMAYDI: stanza-create'dan oldingi
    boshlang'ich xatolar kutilgan. Kechikish — "bo'sh turgan vaqt" emas, balki arxivlanmagan
    TUGALLANGAN segmentlar mavjudligi (joriy yozilayotgan segment arxivga yaroqsiz) va oxirgi
    arxivdan RPO + ARCHIVER_GRACE o'tganligi."""
    if st.archive_mode == "off":
        return "skipped", [], []
    problems: list[Problem] = []
    notes: list[str] = []
    rpo_min = int(RPO.total_seconds() // 60)
    if not timedelta(0) < st.archive_timeout <= RPO:
        problems.append(Problem(
            "archive_timeout_invalid", "warning",
            f"archive_timeout должен быть в пределах 1 с — {rpo_min} мин (RPO), "
            f"сейчас {int(st.archive_timeout.total_seconds())} с"))
    if st.last_failed is not None and (
        st.last_archived is None or st.last_failed > st.last_archived
    ):
        problems.append(Problem("wal_archiver_failed", "critical",
                                "Последняя попытка архивации WAL завершилась ошибкой"))
        return "alarm", problems, notes
    pending = _completed_unarchived(st, notes)
    limit = RPO + ARCHIVER_GRACE
    # Sozlangan RPO'dan kam ishlagan server hali segment arxivlashga ulgurmagan.
    since = st.last_archived if st.last_archived is not None else st.started
    if pending and st.now - since > limit:
        problems.append(Problem(
            "wal_archiver_lag", "critical",
            f"Есть неархивированные завершённые сегменты WAL, последняя архивация более "
            f"{int(limit.total_seconds() // 60)} мин назад — RPO {rpo_min} мин под угрозой"))
    return ("alarm" if problems else "ok"), problems, notes


def _completed_unarchived(st: ArchiverState, notes: list[str]) -> bool:
    if st.current_wal is None:
        return False
    cur_tl, cur = _segno(st.current_wal, st.segment_bytes)
    if st.last_archived_wal is None:
        # Statistika avariyada nollanadi: undan kechikish xulosa qilinmaydi (zaxira yoshi qoplaydi).
        notes.append("wal_archiver: archiver stats empty (fresh start or crash reset); "
                     "WAL safety covered by backup age")
        return False
    name = st.last_archived_wal.split(".")[0]
    if not WAL_NAME_RE.fullmatch(name):  # masalan 00000003.history
        notes.append("wal_archiver: timeline changed, lag check skipped")
        return False
    last_tl, last = _segno(name, st.segment_bytes)
    if cur_tl != last_tl:
        notes.append("wal_archiver: timeline changed, lag check skipped")
        return False
    return cur - last > 1


def _next_month(now: datetime) -> str:
    first = now.astimezone(UTC).replace(day=1)
    return (first + timedelta(days=32)).strftime("%Y%m")


def ops_check(
    now: datetime | None = None,
    tls_cert: Path | None = None,
    app_clock: Callable[[], datetime] = _utcnow,
    notes: list[str] | None = None,
    env: str | None = None,
    collected: list[Problem] | None = None,
) -> list[Problem]:
    """`notes` (ixtiyoriy) — muammo bo'lmagan ma'lumot qatorlari (masalan, `skipped` qoidalar).
    `env` — standart `Settings.env` (test uchun almashtiriladi). `collected` — chaqiruvchining
    ro'yxati: keyingi qadam xato bersa ham topilgan muammolar yo'qolmasin."""
    now = now or _utcnow()
    env = env or get_settings().env
    problems: list[Problem] = collected if collected is not None else []
    with get_engine("app").connect() as conn:
        def _days(key: str) -> timedelta:
            return timedelta(days=int(sysconfig.current(conn, key)))

        restore_max_age = _days("ops.restore_max_age_days")
        dek_max_age = _days("ops.dek_max_age_days")
        tls_warn, tls_critical = _days("ops.tls_warn_days"), _days("ops.tls_critical_days")
        skew_max = timedelta(seconds=int(sysconfig.current(conn, "ops.clock_skew_max_seconds")))
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
            "SELECT count(*) FROM core.etl_requests WHERE "
            "(status = 'pending' AND requested_at < :p) "
            "OR (status = 'running' AND requested_at < :r)"
        ), {"p": now - ETL_REQUEST_STUCK, "r": now - ETL_RUNNING_STUCK}).scalar_one())
        if stuck:
            minutes = int(ETL_REQUEST_STUCK.total_seconds() // 60)
            problems.append(Problem(
                "etl_request_stuck", "warning",
                f"Запросов загрузки в очереди дольше {minutes} минут "
                f"(или в работе дольше {int(ETL_RUNNING_STUCK.total_seconds() // 3600)} ч): "
                f"{stuck}"))
        problems.extend(check_restore(last_restore_test(conn), now, max_age=restore_max_age))
        if env == "prod":
            # seed-load hisoblari: ochiq parol va TOTP siri (devtools) — prod'da bo'lmasligi shart.
            load_users = int(conn.execute(
                text("SELECT count(*) FROM core.users WHERE starts_with(username, :p)"),
                {"p": LOAD_PREFIX},
            ).scalar_one())
            if load_users:
                problems.append(Problem(
                    "load_users_present", "critical",
                    f"В БД {load_users} нагрузочных учётных записей {LOAD_PREFIX}* "
                    "с известным паролем — удалите: python -m app.devtools seed-load --purge "
                    "(только в dev/test) или вручную"))
        rows = conn.execute(text(
            "SELECT purpose, created_at FROM core.crypto_keys "
            "WHERE status = 'active' ORDER BY purpose"))
        for purpose, created_at in rows:
            if now - created_at > dek_max_age:
                problems.append(Problem(
                    "key_rotation_due", "warning",
                    f"Ключ {purpose}: активная версия старше {dek_max_age.days} дней"))
        row = conn.execute(text(
            "SELECT current_setting('archive_mode'), "
            "extract(epoch FROM current_setting('archive_timeout')::interval), "
            "a.last_archived_wal, a.last_archived_time, a.last_failed_time, "
            "CASE WHEN pg_is_in_recovery() THEN NULL "
            "ELSE pg_walfile_name(pg_current_wal_lsn()) END, "
            "pg_size_bytes(current_setting('wal_segment_size')), "
            "pg_postmaster_start_time(), clock_timestamp() FROM pg_stat_archiver a"
        )).one()
        arch = ArchiverState(
            archive_mode=row[0], archive_timeout=timedelta(seconds=float(row[1])),
            last_archived_wal=row[2], last_archived=row[3], last_failed=row[4],
            current_wal=row[5], segment_bytes=int(row[6]), started=row[7], now=row[8])
        status, found, found_notes = check_archiver(arch)
        problems.extend(found)
        if notes is not None:
            notes.extend(found_notes)
            if status == "skipped":
                notes.append("wal_archiver: skipped (archive_mode=off)")
        db_now: datetime = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
    skew = abs(db_now - app_clock())
    if skew > skew_max:
        problems.append(Problem(
            "clock_skew", "critical",
            f"Часы приложения и СУБД расходятся на {int(skew.total_seconds())} с — "
            "проверьте chrony/NTP"))
    if tls_cert is not None:
        try:
            problems.extend(check_tls(tls_cert, now, warn=tls_warn, critical=tls_critical))
        except Exception as exc:  # нечитаемый сертификат не должен скрыть найденные замечания
            problems.append(Problem("tls_cert_unreadable", "critical",
                                    f"Не удалось проверить сертификат: {type(exc).__name__}"))
    return problems


def report(problems: list[Problem]) -> str:
    if not problems:
        return "ops-check: замечаний нет"
    return "\n".join(f"[{p.level.upper()}] {p.code}: {p.message}" for p in problems)
