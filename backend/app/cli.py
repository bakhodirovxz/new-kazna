"""Operator buyruqlari: python -m app.cli <buyruq>.

create-admin   — birinchi administrator (vaqtinchalik parol bir marta chiqariladi)
rotate-key     — DEK rotatsiyasi + qayta shifrlash
retire-keys    — ishlatilmayotgan eski DEK'larni yo'q qilish
rewrap-keys    — KEK rotatsiyasi (keyin master_kek sirini almashtirib, qayta ishga tushiring)
audit-verify   — audit zanjirini tekshirish (buzilgan bo'lsa chiqish kodi 2)
cleanup        — eskirgan sessiya va 2FA challenge'larni o'chirish

`retire-keys` va `rewrap-keys` `wrapped_key` ustunini bo'shatadi/qayta yozadi — bu ustunga
`ugk_app`ning yozish huquqi yo'q (crypto-shredding'dan himoya, spec 3.5), shuning uchun bu
ikki buyruq jadval egasi — `ugk_migrator` — ulanishida ishlaydi. Dev'da `api` konteyneriga
migrator siri berilmagan: shu buyruqlarni `docker compose ... run --rm migrate
python -m app.cli retire-keys` orqali ishga tushiring (README'ga qarang).
"""

from __future__ import annotations

import argparse
import base64
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, or_, select

from app.audit.service import AuditAction, AuditEvent, record, verify_chain_snapshot
from app.auth import passwords
from app.auth.models import MfaChallenge, Position, User, UserSession
from app.auth.permissions import ADMIN_ROLE
from app.auth.service import normalize_username
from app.bootstrap import bootstrap_runtime
from app.core import keystore
from app.core.config import get_settings
from app.core.crypto import Purpose
from app.core.db import get_engine, new_session
from app.core.reencrypt import reencrypt, retire_unused


def _out(message: str) -> None:
    sys.stdout.write(message + "\n")


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
        db.add(User(username=uname, full_name=full_name, position_id=position_id,
                    password_hash=passwords.hash_password(temporary),
                    password_changed_at=datetime.now(UTC), must_change_password=True))
        db.commit()
    record(AuditEvent(
        action=AuditAction.USER_CREATED, user_id=None,
        details={"username": uname, "via": "cli"},
    ))
    _out(f"Administrator yaratildi: {uname}")
    _out(f"Vaqtinchalik parol: {temporary}")
    _out("Birinchi kirishda 2FA ulanadi va parol almashtiriladi.")
    return 0


def _rotate(purpose: Purpose) -> int:
    kek = get_settings().key_bytes("master_kek")
    with get_engine("app").begin() as conn:
        version = keystore.rotate(conn, kek, purpose)
        count = reencrypt(conn, keystore.load_keyring(conn, kek), purpose)
    keystore.invalidate_keyring()
    record(AuditEvent(
        action=AuditAction.KEY_ROTATED, user_id=None, object_type="key",
        object_id=purpose.value, details={"version": version, "reencrypted": count, "via": "cli"},
    ))
    _out(f"{purpose.value}: yangi versiya {version}, qayta shifrlandi: {count}")
    return 0


def _retire(grace_minutes: int) -> int:
    with get_engine("migrator").begin() as conn:
        for purpose in Purpose:
            retired = retire_unused(conn, purpose, timedelta(minutes=grace_minutes))
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
    with get_engine("migrator").begin() as conn:
        count = keystore.rewrap_all(conn, get_settings().key_bytes("master_kek"), new_kek)
    record(AuditEvent(
        action=AuditAction.KEY_REWRAPPED, user_id=None, details={"count": count, "via": "cli"},
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
    now = datetime.now(UTC)
    with new_session() as db:
        challenges = db.execute(
            delete(MfaChallenge).where(MfaChallenge.expires_at < now - timedelta(days=1))
        ).rowcount  # type: ignore[attr-defined]
        old = now - timedelta(days=30)
        stale = db.execute(
            delete(UserSession).where(
                or_(UserSession.absolute_expires_at < old, UserSession.revoked_at < old)
            )
        ).rowcount  # type: ignore[attr-defined]
        db.commit()
    _out(f"o'chirildi: challenge={challenges}, sessiya={stale}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin")
    p.add_argument("--username", required=True)
    p.add_argument("--full-name", required=True)
    p = sub.add_parser("rotate-key")
    p.add_argument("--purpose", required=True, choices=[x.value for x in Purpose])
    p = sub.add_parser("retire-keys")
    p.add_argument("--grace-minutes", type=int, default=10)
    p = sub.add_parser("rewrap-keys")
    p.add_argument("--new-kek-file", type=Path, required=True)
    sub.add_parser("audit-verify")
    sub.add_parser("cleanup")
    args = parser.parse_args(argv)

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
    return _cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
