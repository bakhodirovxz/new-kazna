"""Operator buyruqlari: python -m app.cli <buyruq>.

create-admin   — birinchi administrator (vaqtinchalik parol bir marta chiqariladi)
rotate-key     — DEK rotatsiyasi + qayta shifrlash
retire-keys    — ishlatilmayotgan eski DEK'larni yo'q qilish
rewrap-keys    — KEK rotatsiyasi (keyin master_kek sirini almashtirib, qayta ishga tushiring)
audit-verify   — audit zanjirini tekshirish (buzilgan bo'lsa chiqish kodi 2)
cleanup        — eskirgan sessiya, 2FA challenge va staging qatorlarini o'chirish
etl-run        — ETL yuklash: --source synthetic|file --mode full|incremental [--no-retry]
               [--allow-full-replace] (file + full uchun majburiy)
rollback-build — aktiv build'ni oldingisiga (yoki --build ID ga) qaytarish
restore-test-record — tiklash testi natijasini yozish (scripts/restore_test.sh chaqiradi)
restore-test-status — oxirgi tiklash testi: 0 — joyida, 1 — yo'q/xato/eskirgan
ops-check      — ekspluatatsiya tekshiruvi: [--json] [--notify] [--tls-cert PATH] [--extra TEXT]

`retire-keys` va `rewrap-keys` `wrapped_key` ustunini bo'shatadi/qayta yozadi — bu ustunga
`ugk_app`ning yozish huquqi yo'q (crypto-shredding'dan himoya, spec 3.5), shuning uchun bu
ikki buyruq jadval egasi — `ugk_migrator` — ulanishida ishlaydi. `rotate-key` ham endi
qisman migrator ulanishidan foydalanadi (fix r1, I1): `dwh.*` shifrlangan rekvizitlar
(`dwh.dim_counterparty.inn_enc`, `dwh.dim_bank.account_enc`) `ugk_app`ga umuman ochiq emas,
shuning uchun ularni faqat migrator ulanishi qayta shifrlay oladi. Dev'da `api` konteyneriga
migrator siri berilmagan: shu uch buyruqni `docker compose ... run --rm migrate
python -m app.cli rotate-key --purpose ...` (yoki `retire-keys`/`rewrap-keys`) orqali ishga
tushiring (README'ga qarang).

Har bir kalit-mutatsiya buyrug'ida (`rotate-key`, `retire-keys`, `rewrap-keys`) tartib
muhim: avval haqiqiy mutatsiya va uning committi (`with engine.begin(): ...` bloki
muvaffaqiyatli tugaydi), SO'NGGINA audit yozuvi ("ok" natija bilan). Xato bo'lsa — audit
"fail" natija bilan yoziladi (kalit materialisiz, faqat maqsad/xato turi) va istisno qayta
ko'tariladi (chiqish kodi nolga teng bo'lmaydi). `restore-test-record` ham shunday:
avval yozuv committi, so'ngra audit; audit `result` — OPERATSIYA natijasi (yozildi), tiklash
testining natijasi esa `details.outcome` da.

`ops-check` va `restore-test-status` `bootstrap_runtime()` DAN OLDIN ishlaydi: ular faqat
o'qiydi (kalit zanjiri kerak emas), bootstrap esa audit partitsiyalarini oldindan yaratib
`audit_partition_missing` ni yashirardi va DB o'chiq bo'lsa ogohlantirishdan oldin yiqilardi.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app import ops
from app.audit.service import AuditAction, AuditEvent, record, verify_chain_snapshot
from app.auth import passwords
from app.auth.models import Position, User
from app.auth.permissions import ADMIN_ROLE
from app.auth.service import normalize_username
from app.bootstrap import bootstrap_runtime
from app.core import keystore
from app.core.config import ConfigError, get_settings
from app.core.crypto import Purpose
from app.core.db import get_engine, new_session
from app.core.errors import ConflictError
from app.core.reencrypt import reencrypt, retire_unused
from app.dwh import builds
from app.etl.connectors import make_connector
from app.etl.db import etl_transaction
from app.etl.errors import FILE_FULL_REFUSED, EtlBusyError, safe_error
from app.etl.notify import Notification, build_notifier
from app.etl.retry import RETRY_DELAYS
from app.etl.runner import ETL_LOCK, Runner
from app.etl.types import Mode
from app.maintenance import cleanup_sessions, cleanup_staging

MIN_GRACE_MINUTES = 10
MAX_RESTORE_SECONDS = 7 * 24 * 3600
# pgBackRest yorlig'i: to'liq `YYYYMMDD-HHMMSSF`, diff/incr `<to'liq>_YYYYMMDD-HHMMSS[DI]`;
# `none` — bo'sh repo (restore_test.sh 3-kod) uchun.
BACKUP_LABEL_RE = re.compile(r"^(none|\d{8}-\d{6}F(_\d{8}-\d{6}[DI])?)$")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
MAX_DETAILS = 2000


def _out(message: str) -> None:
    sys.stdout.write(message + "\n")


def _grace_minutes(value: str) -> int:
    n = int(value)
    if n < MIN_GRACE_MINUTES:
        raise argparse.ArgumentTypeError(
            f"--grace-minutes >= {MIN_GRACE_MINUTES} bo'lishi kerak"
        )
    return n


def _duration(value: str) -> int:
    n = int(value)
    if not 0 <= n <= MAX_RESTORE_SECONDS:
        raise argparse.ArgumentTypeError(
            f"--duration-seconds 0..{MAX_RESTORE_SECONDS} bo'lishi kerak")
    return n


def _backup_label(value: str) -> str:
    if not BACKUP_LABEL_RE.match(value):
        raise argparse.ArgumentTypeError(
            "--backup pgBackRest yorlig'i (yoki 'none') bo'lishi kerak")
    return value


def _details(value: str) -> str:
    if len(value) > MAX_DETAILS or CONTROL_RE.search(value):
        raise argparse.ArgumentTypeError(
            f"--details {MAX_DETAILS} belgidan oshmasligi va boshqaruv belgilarisiz bo'lishi kerak")
    return value


def _create_admin(username: str, full_name: str) -> int:
    uname = normalize_username(username)
    with new_session() as db:
        if db.execute(select(User.id).where(User.username == uname)).first() is not None:
            _out(f"Xato: '{uname}' allaqachon mavjud")
            return 1
        position_id = db.execute(
            select(Position.id).where(Position.code == ADMIN_ROLE)
        ).scalar_one()
        temporary = passwords.generate_temporary_password()
        user = User(username=uname, full_name=full_name, position_id=position_id,
                    password_hash=passwords.hash_password(temporary),
                    password_changed_at=datetime.now(UTC), must_change_password=True)
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            _out(f"Xato: '{uname}' allaqachon mavjud")
            return 1
        user_id = user.id
    record(AuditEvent(
        action=AuditAction.USER_CREATED, user_id=None, object_type="user",
        object_id=str(user_id), details={"username": uname, "via": "cli"},
    ))
    _out(f"Administrator yaratildi: {uname}")
    _out(f"Vaqtinchalik parol: {temporary}")
    _out("Birinchi kirishda 2FA ulanadi va parol almashtiriladi.")
    return 0


ETL_BUSY_KEYS = ("Xato: ETL yuklash bajarilmoqda — kalitlarni o'zgartirish rad etildi "
                 "(keyinroq urinib ko'ring)")


@contextmanager
def _etl_lock() -> Iterator[None]:
    """I3: ETL runner'ning global advisory lock'i (`ETL_LOCK`) ushlab turiladi — aks holda
    retire/rotate bosqichma-bosqich yuklanayotgan staging'ni crypto-shred qilishi mumkin."""
    with get_engine("migrator").connect() as raw:
        conn = raw.execution_options(isolation_level="AUTOCOMMIT")
        if not conn.execute(text("SELECT pg_try_advisory_lock(hashtext(:k))"),
                            {"k": ETL_LOCK}).scalar_one():
            raise EtlBusyError
        try:
            yield
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": ETL_LOCK})


def _kek_id(kek: bytes) -> str:
    """KEK'ning ochiq identifikatori (audit `mask()` o'tkazadi) — kalitni oshkor qilmaydi."""
    return hashlib.sha256(b"ugk-kek-id|" + kek).hexdigest()[:16]


def _rotate(purpose: Purpose) -> int:
    """DEK rotatsiyasi + qayta shifrlash.

    Fix r1 (I1): `ugk_app`ning `dwh.*` shifrlangan rekvizitlarga (role="migrator") hech
    qanday huquqi yo'q, shuning uchun ikki bosqich: avval "app" ulanishida versiya
    yaratiladi va `core.*` (role="app") ustunlar qayta shifrlanadi (bitta tranzaksiya),
    so'ng "migrator" ulanishida `dwh.*` (role="migrator") ustunlar alohida qayta
    shifrlanadi. Bu buyruq faqat `migrate` konteynerida (migrator siri bor joyda) ishga
    tushiriladi — README'ga qarang.
    """
    kek = get_settings().key_bytes("master_kek")
    try:
        with _etl_lock():
            with get_engine("app").begin() as conn:
                version = keystore.rotate(conn, kek, purpose)
                count = reencrypt(conn, keystore.load_keyring(conn, kek), purpose, role="app")
            with get_engine("migrator").begin() as conn:
                count += reencrypt(conn, keystore.load_keyring(conn, kek), purpose,
                                   role="migrator")
    except Exception as exc:
        record(AuditEvent(
            action=AuditAction.KEY_ROTATED, user_id=None, result="fail", object_type="key",
            object_id=purpose.value,
            details={"purpose": purpose.value, "error": type(exc).__name__, "via": "cli"},
        ))
        if isinstance(exc, EtlBusyError):
            _out(ETL_BUSY_KEYS)
            return 3
        raise
    keystore.invalidate_keyring()
    record(AuditEvent(
        action=AuditAction.KEY_ROTATED, user_id=None, object_type="key",
        object_id=purpose.value, details={"version": version, "reencrypted": count, "via": "cli"},
    ))
    _out(f"{purpose.value}: yangi versiya {version}, qayta shifrlandi: {count}")
    return 0


def _retire(grace_minutes: int) -> int:
    grace = timedelta(minutes=grace_minutes)
    try:
        with _etl_lock(), get_engine("migrator").begin() as conn:
            retired_by_purpose = {p: retire_unused(conn, p, grace) for p in Purpose}
    except Exception as exc:
        record(AuditEvent(
            action=AuditAction.KEY_RETIRED, user_id=None, result="fail",
            details={"grace_minutes": grace_minutes, "error": type(exc).__name__, "via": "cli"},
        ))
        if isinstance(exc, EtlBusyError):
            _out(ETL_BUSY_KEYS)
            return 3
        raise
    for purpose, retired in retired_by_purpose.items():
        if retired:
            record(AuditEvent(
                action=AuditAction.KEY_RETIRED, user_id=None, object_type="key",
                object_id=purpose.value, details={"versions": retired, "via": "cli"},
            ))
            _out(f"{purpose.value}: yo'q qilindi {retired}")
    return 0


def _rewrap(new_kek_file: Path) -> int:
    new_kek = base64.b64decode(new_kek_file.read_text().strip(), validate=True)
    if len(new_kek) != 32:
        _out("Xato: yangi KEK 32 bayt bo'lishi kerak")
        return 1
    current_kek = get_settings().key_bytes("master_kek")
    if hmac.compare_digest(new_kek, current_kek):
        _out("Xato: yangi KEK joriy KEK bilan bir xil")
        return 1
    try:
        with get_engine("migrator").begin() as conn:
            count = keystore.rewrap_all(conn, current_kek, new_kek)
    except Exception as exc:
        record(AuditEvent(
            action=AuditAction.KEY_REWRAPPED, user_id=None, result="fail",
            details={"error": type(exc).__name__, "via": "cli"},
        ))
        raise
    # Baza allaqachon YANGI KEK bilan o'ralgan, lekin `Settings.master_kek` operator uni
    # almashtirib qayta ishga tushirmaguncha hali ESKI qiymatda turadi — shuning uchun
    # keshni ESKI KEK bilan qayta yuklamaymiz (u endi hech nimani ocha olmaydi), balki
    # qo'lda YANGI KEK bilan ochib, audit yozuvi (AUDIT_CHAIN HMAC kaliti kerak) uchun
    # jarayon keshiga o'rnatamiz.
    keystore.invalidate_keyring()
    with get_engine("migrator").connect() as conn:
        ring = keystore.load_keyring(conn, new_kek)
    keystore.set_keyring_for_process(ring)
    record(AuditEvent(
        action=AuditAction.KEY_REWRAPPED, user_id=None,
        details={"count": count, "fingerprint": _kek_id(new_kek), "via": "cli"},
    ))
    _out(f"{count} ta kalit qayta o'raldi. Endi master_kek sirini almashtirib, "
         "servislarni qayta ishga tushiring.")
    return 0


def _audit_verify() -> int:
    report = verify_chain_snapshot()
    _out(f"ok={report.ok} checked={report.checked} first_bad_id={report.first_bad_id}")
    if report.bad_ids:
        _out(f"bad_ids (birinchi 20): {report.bad_ids[:20]}")
    return 0 if report.ok else 2


def _cleanup() -> int:
    challenges, stale = cleanup_sessions()
    staged = cleanup_staging()
    _out(f"o'chirildi: challenge={challenges}, sessiya={stale}, staging={staged}")
    return 0


def _etl_run(source: str, mode: str, no_retry: bool, allow_full_replace: bool = False) -> int:
    if source == "file" and mode == "full" and not allow_full_replace:
        _out(f"Xato: {FILE_FULL_REFUSED}")
        return 2
    try:
        connector = make_connector(source)
    except (ValueError, ConfigError) as exc:
        _out(f"Xato: {exc}")
        return 2
    runner = Runner(connector, mode=Mode(mode), notifier=build_notifier(get_settings()),
                    delays=() if no_retry else RETRY_DELAYS)
    try:
        result = runner.run()
    except EtlBusyError:
        _out("Xato: boshqa yuklash bajarilmoqda")
        return 3
    except Exception as exc:  # A14.8: xom matn yo'q, faqat sinf nomi (+ SQLSTATE)
        _out(f"Xato: {safe_error(exc)}")
        return 1
    _out(f"run={result.run_id} status={result.status} build={result.build_id}")
    if result.error:
        _out(f"xato: {result.error}")
    return 0 if result.status == "success" else 1


def _rollback(build_id: int | None) -> int:
    try:
        with etl_transaction() as conn:
            previous = builds.active_build(conn)
            target = builds.rollback(conn, build_id)
    except ConflictError:
        _out("Xato: bunday build yo'q yoki unga qaytib bo'lmaydi")
        return 1
    record(AuditEvent(action=AuditAction.BUILD_ROLLED_BACK, object_type="build",
                      object_id=str(target),
                      details={"from": previous, "to": target, "via": "cli"}))
    _out(f"Aktiv build: {previous} → {target}")
    return 0


def _restore_record(result: str, duration: int, backup: str, details: str) -> int:
    status: ops.RestoreStatus = "ok" if result == "ok" else "fail"
    restore = ops.RestoreResult(at=datetime.now(UTC), result=status, duration_seconds=duration,
                                backup=backup, details=details)
    with get_engine("app").begin() as conn:
        version = ops.record_restore_test(conn, restore)
    record(AuditEvent(action=AuditAction.RESTORE_TEST_RECORDED,
                      object_type="restore_test", object_id=backup[:64],
                      details={"outcome": status, "duration_seconds": duration,
                               "rto_ok": restore.rto_ok, "version": version, "via": "cli"}))
    _out(f"last_restore_test v{version}: {status}, {duration} s, zaxira {backup}")
    return 0


def _restore_status() -> int:
    with get_engine("app").connect() as conn:
        value = ops.last_restore_test(conn)
    _out(json.dumps(value, ensure_ascii=False, indent=2) if value is not None else "null")
    return 1 if ops.check_restore(value, datetime.now(UTC)) else 0


def _ops_check(as_json: bool, notify: bool, tls_cert: Path | None, extra: list[str]) -> int:
    problems = [ops.Problem("host", "critical", item) for item in extra]
    notes: list[str] = []
    try:
        problems.extend(ops.ops_check(tls_cert=tls_cert, notes=notes))
    except Exception as exc:  # DB o'chiq bo'lsa ham xabar ketishi shart; xom matn yo'q (DSN)
        problems.append(ops.Problem("ops_check_error", "critical", safe_error(exc)))
    if as_json:
        _out(json.dumps({"problems": [asdict(p) for p in problems], "notes": notes},
                        ensure_ascii=False))
    else:
        _out(ops.report(problems))
        for note in notes:
            _out(note)
    if notify and problems:
        build_notifier(get_settings()).notify(Notification(
            "ops_check", f"UGEKAZNA: замечаний — {len(problems)}", ops.report(problems)))
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin")
    p.add_argument("--username", required=True)
    p.add_argument("--full-name", required=True)
    p = sub.add_parser("rotate-key")
    p.add_argument("--purpose", required=True, choices=[x.value for x in Purpose])
    p = sub.add_parser("retire-keys")
    p.add_argument("--grace-minutes", type=_grace_minutes, default=MIN_GRACE_MINUTES)
    p = sub.add_parser("rewrap-keys")
    p.add_argument("--new-kek-file", type=Path, required=True)
    sub.add_parser("audit-verify")
    sub.add_parser("cleanup")
    p = sub.add_parser("etl-run")
    p.add_argument("--source", required=True)
    p.add_argument("--mode", choices=["full", "incremental"], default="incremental")
    p.add_argument("--no-retry", action="store_true")
    p.add_argument("--allow-full-replace", action="store_true")
    p = sub.add_parser("rollback-build")
    p.add_argument("--build", type=int, default=None)
    p = sub.add_parser("restore-test-record")
    p.add_argument("--result", choices=["ok", "fail"], required=True)
    p.add_argument("--duration-seconds", type=_duration, required=True)
    p.add_argument("--backup", type=_backup_label, required=True)
    p.add_argument("--details", type=_details, default="")
    sub.add_parser("restore-test-status")
    p = sub.add_parser("ops-check")
    p.add_argument("--json", action="store_true")
    p.add_argument("--notify", action="store_true")
    p.add_argument("--tls-cert", type=Path, default=None)
    p.add_argument("--extra", action="append", default=[])
    args = parser.parse_args(argv)

    if args.command == "restore-test-status":
        return _restore_status()
    if args.command == "ops-check":
        return _ops_check(args.json, args.notify, args.tls_cert, args.extra)
    bootstrap_runtime()
    if args.command == "create-admin":
        return _create_admin(args.username, args.full_name)
    if args.command == "rotate-key":
        return _rotate(Purpose(args.purpose))
    if args.command == "retire-keys":
        return _retire(args.grace_minutes)
    if args.command == "rewrap-keys":
        return _rewrap(args.new_kek_file)
    if args.command == "audit-verify":
        return _audit_verify()
    if args.command == "etl-run":
        return _etl_run(args.source, args.mode, args.no_retry, args.allow_full_replace)
    if args.command == "rollback-build":
        return _rollback(args.build)
    if args.command == "restore-test-record":
        return _restore_record(args.result, args.duration_seconds, args.backup, args.details)
    return _cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
