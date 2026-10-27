"""Integratsiyalar reyestri va sirlar ombori (spec 2026-10-26, 3.5–3.6, 4.2).

Sir faqat ishlatish joyida ochiladi (`secret`) va API/log/audit'ga chiqmaydi. Manzil kaliti
panelda qayta belgilangan bo'lsa env'dagi sir fallback bo'lmaydi — hisob ma'lumotini boshqa
serverga yo'naltirib bo'lmaydi (credential redirect).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core import keystore, sysconfig
from app.core.config import get_settings
from app.core.crypto import Purpose

SecretState = Literal["panel", "env", "none"]
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class SecretDef:
    name: str
    title: str
    env: str | None = None  # Settings SecretStr maydoni — bootstrap
    pattern: str | None = None
    max_length: int = 4096

    def validate(self, plain: str) -> str:
        if (not plain or len(plain) > self.max_length or _CONTROL.search(plain)
                or (self.pattern is not None and not re.fullmatch(self.pattern, plain))):
            raise ValueError(f"{self.name}: yaroqsiz qiymat")
        return plain


@dataclass(frozen=True, slots=True)
class IntegrationDef:
    name: str
    title: str
    fields: tuple[str, ...]  # sysconfig kalitlari (category="integrations")
    endpoint: tuple[str, ...]  # o'zgarsa sirlar tozalanadi
    secrets: tuple[SecretDef, ...]
    check_in: Literal["worker", "api"] = "worker"  # probe qayerda (egress bor joyda)


_ALL: tuple[IntegrationDef, ...] = (
    IntegrationDef(
        "smtp", "Почтовый сервер (SMTP)",
        fields=("smtp.host", "smtp.port", "smtp.from", "smtp.user", "smtp.starttls", "smtp.ssl"),
        endpoint=("smtp.host", "smtp.port"),
        secrets=(SecretDef("smtp.password", "Пароль SMTP", env="smtp_password"),)),
    IntegrationDef("askue_live", "Текущая мощность (treplex)", fields=("askue.live_url",),
                   endpoint=("askue.live_url",), secrets=()),
    IntegrationDef(
        "onec_sklad", "1С: склад", fields=("onec_sklad.base_url",),
        endpoint=("onec_sklad.base_url",),
        secrets=(SecretDef("onec_sklad.username", "Пользователь 1С (склад)", max_length=128),
                 SecretDef("onec_sklad.password", "Пароль 1С (склад)"))),
)
INTEGRATIONS: dict[str, IntegrationDef] = {i.name: i for i in _ALL}
SECRETS: dict[str, tuple[IntegrationDef, SecretDef]] = {
    s.name: (i, s) for i in _ALL for s in i.secrets}


def secret_aad(name: str) -> str:
    return f"core.integration_credentials.value_enc:{name}"  # = reencrypt EncryptedColumn.aad


def _env_secret(sd: SecretDef) -> str:
    if sd.env is None:
        return ""
    raw = getattr(get_settings(), sd.env)
    return raw.get_secret_value() if isinstance(raw, SecretStr) else str(raw)


def _endpoint_overridden(conn: Connection, integ: IntegrationDef) -> bool:
    return conn.execute(text("SELECT 1 FROM core.settings WHERE is_current AND key = ANY(:k) "
                             "LIMIT 1"), {"k": list(integ.endpoint)}).first() is not None


def _row(conn: Connection, name: str) -> Any:
    return conn.execute(text("SELECT value_enc, updated_at, updated_by FROM "
                             "core.integration_credentials WHERE name = :n"), {"n": name}).first()


def secret(conn: Connection, name: str) -> str:
    """Ochiq sir — faqat konnektor/notifier ichida ishlatiladi."""
    integ, sd = SECRETS[name]
    row = _row(conn, name)
    if row is not None:
        return keystore.decrypt_str(Purpose.INTEGRATION, row.value_enc, secret_aad(name))
    return "" if _endpoint_overridden(conn, integ) else _env_secret(sd)


def secret_state(conn: Connection, name: str) -> tuple[SecretState, datetime | None, int | None]:
    integ, sd = SECRETS[name]
    row = _row(conn, name)
    if row is not None:
        return "panel", row.updated_at, row.updated_by
    if _env_secret(sd) and not _endpoint_overridden(conn, integ):
        return "env", None, None
    return "none", None, None


def store_secret(conn: Connection, name: str, plain: str, user_id: int | None) -> None:
    _integ, sd = SECRETS[name]
    blob = keystore.encrypt_str(Purpose.INTEGRATION, sd.validate(plain), secret_aad(name))
    conn.execute(text(
        "INSERT INTO core.integration_credentials (name, value_enc, updated_by) "
        "VALUES (:n, :b, :u) ON CONFLICT (name) DO UPDATE SET value_enc = EXCLUDED.value_enc, "
        "updated_by = EXCLUDED.updated_by, updated_at = now()"),
        {"n": name, "b": blob, "u": user_id})


def clear_secret(conn: Connection, name: str) -> bool:
    return conn.execute(text("DELETE FROM core.integration_credentials WHERE name = :n "
                             "RETURNING name"), {"n": name}).first() is not None


def field_values(conn: Connection, name: str) -> dict[str, Any]:
    return {key: sysconfig.current(conn, key) for key in INTEGRATIONS[name].fields}


def _smtp_rule(conn: Connection) -> tuple[str, str] | None:
    tls = bool(sysconfig.current(conn, "smtp.starttls")) or bool(
        sysconfig.current(conn, "smtp.ssl"))
    if tls or not secret(conn, "smtp.password"):
        return None
    return ("insecure_smtp", "smtp.starttls")


# Integratsiya darajasidagi tekshiruv: (xato kodi, maydon) yoki None. Saqlashdan oldin, shu
# tranzaksiyada (yangi qiymatlar bilan) chaqiriladi.
def _onec_sklad_rule(conn: Connection) -> tuple[str, str] | None:
    # shortcut: S1 `onec_allow_http` bayrog'i bu bazada yo'q — http:// har doim rad etiladi.
    if str(sysconfig.current(conn, "onec_sklad.base_url")).startswith("http://"):
        return ("insecure_http", "onec_sklad.base_url")
    return None


RULES: dict[str, Callable[[Connection], tuple[str, str] | None]] = {
    "smtp": _smtp_rule, "onec_sklad": _onec_sklad_rule}
