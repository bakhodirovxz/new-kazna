"""Faqat dev/test muhiti uchun yordamchi buyruqlar.

    python -m app.devtools seed-e2e
    python -m app.devtools seed-load --users 100
    python -m app.devtools seed-load --purge

`seed-e2e` Playwright E2E testlari uchun ma'lum parol va ma'lum TOTP sirli
foydalanuvchilarni yaratadi yoki holatini qayta tiklaydi (idempotent). ENV dev/test
bo'lmasa hech narsa qilmaydi va 2 kodi bilan chiqadi — prod'da bu hisoblar paydo bo'lmaydi.

`seed-load` yuklama testi (k6) uchun `load_NNN` foydalanuvchilarini yaratadi/tiklaydi va har biriga
TAYYOR sessiya ochadi (login'siz); natija — stdout'dagi oxirgi qator, JSON ro'yxat.
`seed-load --purge` ularni (sessiyalar, zaxira kodlar va filial lavozimlari bilan) o'chiradi —
`ugk_migrator` ulanishi kerak (ugk_app'da core.users DELETE huquqi yo'q), masalan `migrate`
konteynerida. Prod'da qolgan `load_*` hisoblarini `ops-check` (`load_users_present`) ko'rsatadi.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.auth import passwords, sessions
from app.auth.models import BackupCode, Position, PositionBranch, Role, User, UserSession
from app.auth.service import totp_aad
from app.bootstrap import bootstrap_runtime
from app.core import keystore
from app.core.crypto import Purpose
from app.core.db import get_engine, new_session

ALLOWED_ENVS = frozenset({"dev", "test"})
E2E_PASSWORD = "E2e-Sinov-Kalit-2026!"  # noqa: S105 -- faqat dev/test E2E qiymati
E2E_TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"  # noqa: S105 -- faqat dev/test


@dataclass(frozen=True, slots=True)
class E2eUser:
    username: str
    full_name: str
    role: str
    totp: bool
    must_change: bool
    branch_ids: tuple[int, ...] = ()


E2E_USERS: tuple[E2eUser, ...] = (
    E2eUser("e2e_admin_390", "Тестов Мобильный", "admin", totp=True, must_change=False),
    E2eUser("e2e_admin_1024", "Тестов Планшетный", "admin", totp=True, must_change=False),
    E2eUser("e2e_admin_1440", "Тестов Настольный", "admin", totp=True, must_change=False),
    E2eUser("e2e_new", "Новиков Сотрудник", "spec_kazna", totp=False, must_change=True),
    # 2FA majburiy emas: TOTP'siz, parol vaqtinchalik emas — "Позже" oqimi uchun
    E2eUser("e2e_skip", "Пропускин Сотрудник", "spec_kazna", totp=False, must_change=False),
    E2eUser(
        "e2e_branch",
        "Филиалов Экономист",
        "economist_filiala",
        totp=True,
        must_change=False,
        branch_ids=(3,),
    ),
)


def _out(message: str) -> None:
    sys.stdout.write(message + "\n")


def _position_id(db: Session, spec: E2eUser) -> int:
    role_id = db.execute(select(Role.id).where(Role.code == spec.role)).scalar_one()
    if not spec.branch_ids:
        # Tizim rollari uchun seed qilingan lavozim (kodi rol kodi bilan bir xil).
        return int(db.execute(select(Position.id).where(Position.code == spec.role)).scalar_one())
    code = f"e2e_{spec.username}"
    position = db.execute(select(Position).where(Position.code == code)).scalar_one_or_none()
    if position is None:
        position = Position(code=code, name=f"E2E: {spec.full_name}", role_id=role_id)
        db.add(position)
        db.flush()
    position.role_id = role_id
    position.is_active = True
    db.execute(delete(PositionBranch).where(PositionBranch.position_id == position.id))
    for branch_id in spec.branch_ids:
        db.add(PositionBranch(position_id=position.id, branch_id=branch_id))
    return int(position.id)


def _upsert(db: Session, spec: E2eUser, password_hash: str, now: datetime) -> User:
    position_id = _position_id(db, spec)
    user = db.execute(select(User).where(User.username == spec.username)).scalar_one_or_none()
    if user is None:
        user = User(
            username=spec.username,
            full_name=spec.full_name,
            position_id=position_id,
            password_hash=password_hash,
            password_changed_at=now,
            must_change_password=spec.must_change,
        )
        db.add(user)
        db.flush()
    user.full_name = spec.full_name
    user.position_id = position_id
    user.password_hash = password_hash
    user.password_changed_at = now
    user.must_change_password = spec.must_change
    user.is_active = True
    user.failed_logins = 0
    user.locked_until = None
    user.totp_last_step = None
    user.totp_enabled = spec.totp
    user.totp_secret_enc = (
        keystore.encrypt_str(Purpose.MFA, E2E_TOTP_SECRET, totp_aad(user.id)) if spec.totp else None
    )
    db.execute(
        update(BackupCode)
        .where(BackupCode.user_id == user.id, BackupCode.used_at.is_(None))
        .values(used_at=now)
    )
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now, revoke_reason="e2e_reset")
    )
    return user


def seed_e2e() -> int:
    # ENV aniq berilgan bo'lishi shart (Settings standarti prod, lekin bu yerda env'ga tayanamiz).
    env = os.environ.get("ENV", "")
    if env not in ALLOWED_ENVS:
        shown = env or "belgilanmagan"
        _out(f"Rad etildi: seed-e2e faqat aniq ENV=dev/test muhitida ishlaydi (ENV={shown})")
        return 2
    bootstrap_runtime()
    now = datetime.now(UTC)
    password_hash = passwords.hash_password(E2E_PASSWORD)
    with new_session() as db:
        for spec in E2E_USERS:
            _upsert(db, spec, password_hash, now)
        db.commit()
    _out("E2E foydalanuvchilari tayyor: " + ", ".join(spec.username for spec in E2E_USERS))
    return 0


LOAD_PREFIX = "load_"
LOAD_MAX_USERS = 500
# Har 3-foydalanuvchi — filial iqtisodchisi (RLS va scope keshi ham yuklansin).
LOAD_BRANCH_EVERY = 3


def load_users(count: int) -> list[E2eUser]:
    users: list[E2eUser] = []
    for i in range(1, count + 1):
        username = f"{LOAD_PREFIX}{i:03d}"
        full_name = f"Нагрузочный {i:03d}"
        if i % LOAD_BRANCH_EVERY == 0:
            branch = 2 + (i // LOAD_BRANCH_EVERY) % 15
            users.append(
                E2eUser(
                    username,
                    full_name,
                    "economist_filiala",
                    totp=True,
                    must_change=False,
                    branch_ids=(branch,),
                )
            )
        else:
            users.append(E2eUser(username, full_name, "rukovodstvo", totp=True, must_change=False))
    return users


def seed_load(count: int) -> list[dict[str, object]]:
    """Yuklama testi foydalanuvchilari va tayyor sessiyalar (docs/ops/load-test.md, Ruling)."""
    bootstrap_runtime()
    now = datetime.now(UTC)
    password_hash = passwords.hash_password(E2E_PASSWORD)
    out: list[dict[str, object]] = []
    with new_session() as db:
        for spec in load_users(count):
            user = _upsert(db, spec, password_hash, now)
            new = sessions.create(db, user.id, "127.0.0.1", "k6-loadtest", now)
            out.append(
                {
                    "username": spec.username,
                    "token": new.token,
                    "csrf": new.csrf,
                    "branches": list(spec.branch_ids),
                }
            )
        db.commit()
    return out


def purge_load() -> int:
    """`load_*` foydalanuvchilarini o'chiradi (sessiyalar, backup kodlar — CASCADE)."""
    with get_engine("migrator").begin() as conn:
        deleted = conn.execute(
            delete(User).where(User.username.startswith(LOAD_PREFIX, autoescape=True))
        ).rowcount
        # _position_id: filial foydalanuvchilari uchun `e2e_<username>` lavozimi yaratilgan.
        conn.execute(
            delete(Position).where(
                Position.code.startswith(f"e2e_{LOAD_PREFIX}", autoescape=True),
                ~select(User.id).where(User.position_id == Position.id).exists(),
            )
        )
    return int(deleted)


def _load_count(value: str) -> int:
    count = int(value)
    if not 1 <= count <= LOAD_MAX_USERS:
        raise argparse.ArgumentTypeError(f"1..{LOAD_MAX_USERS} oralig'ida bo'lishi kerak")
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.devtools")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed-e2e", help="E2E foydalanuvchilarini yaratish/tiklash (faqat dev/test)")
    load = sub.add_parser(
        "seed-load", help="yuklama testi foydalanuvchilari va sessiyalari (faqat dev/test)"
    )
    load.add_argument("--users", type=_load_count, default=100)
    load.add_argument("--purge", action="store_true", help="load_* foydalanuvchilarini o'chirish")
    args = parser.parse_args(argv)
    if args.command == "seed-load":
        # seed_e2e bilan bir xil: Settings standartiga emas, aniq berilgan ENV'ga tayanamiz.
        env = os.environ.get("ENV", "")
        if env not in ALLOWED_ENVS:
            shown = env or "belgilanmagan"
            _out(f"Rad etildi: seed-load faqat aniq ENV=dev/test muhitida ishlaydi (ENV={shown})")
            return 2
        if args.purge:
            _out(f"O'chirildi: {purge_load()} ta {LOAD_PREFIX}* foydalanuvchi")
            return 0
        sys.stdout.write(json.dumps(seed_load(args.users), ensure_ascii=False) + "\n")
        return 0
    return seed_e2e()


if __name__ == "__main__":
    raise SystemExit(main())
