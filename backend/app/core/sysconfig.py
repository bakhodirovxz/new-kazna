"""Tizim sozlamalari reyestri (spec 2026-10-26-admin-settings-design.md, 3–4-bo'limlar).

Har kalit — bitta `SettingDef`: tur va chegaralar (adapter), kategoriya, ruxsat, himoya.
Manba ustuvorligi: `core.settings` (panel) > env/Docker secret (faqat `env` bog'langan
kalitlar) > kod standarti. Har manbadagi qiymat bir xil adapter bilan tekshiriladi —
yaroqsiz bo'lsa keyingi manba olinadi (reliz pollarni qattiqlashtirsa, eski panel qiymati
ularni chetlab o'tolmaydi).
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal

from apscheduler.triggers.cron import CronTrigger
from pydantic import AfterValidator, Field, SecretStr, TypeAdapter
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.permissions import Perm
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.logging import get_logger
from app.dwh.dates import today_tashkent

Kind = Literal["int", "float", "bool", "str", "cron", "date", "list", "json"]
Apply = Literal["live", "next_run"]
Source = Literal["panel", "env", "default"]
KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
EMAIL_RE = r"^[^\s,<>@]+@[^\s,<>@]+\.[^\s,<>@]+$"  # app/core/config.py bilan bir xil
CACHE_TTL = 30.0  # s: boshqa jarayonlar o'zgarishni shu muddatda ko'radi

log = get_logger("ugekazna.sysconfig")


@dataclass(frozen=True, slots=True)
class SettingDef:
    key: str
    default: Any
    adapter: TypeAdapter[Any]
    kind: Kind
    category: str
    title: str
    perm: Perm = Perm.ADMIN_SETTINGS
    guarded: bool = False  # sabab (reason) majburiy
    apply: Apply = "live"
    unit: str = ""
    lo: float | None = None
    hi: float | None = None
    env: str | None = None  # Settings maydoni: bootstrap qiymati, "env" manbai model_fields_set'dan
    env_attr: str | None = None  # qiymat boshqa atributdan olinsa (smtp_to → smtp_recipients)

    @property
    def step_up(self) -> bool:
        """Xavfsizlik va integratsiya kalitlari: sabab + joriy TOTP kodi (ASVS 3.7.1)."""
        return self.guarded and self.perm != Perm.ADMIN_SETTINGS

    def validate(self, value: Any) -> Any:
        try:
            return self.adapter.validate_python(value)
        except PydanticValidationError as exc:
            raise ValueError(f"{self.key}: noto'g'ri qiymat") from exc


def check_cron(value: str) -> str:
    # A4.2: aniq timezone="UTC" — tzlocal qidiruvisiz; worker TASHKENT bilan rejalashtiradi.
    trigger = CronTrigger.from_crontab(value, timezone="UTC")  # noto'g'ri bo'lsa ValueError
    if trigger.get_next_fire_time(None, datetime.now(UTC)) is None:
        raise ValueError("cron hech qachon ishga tushmaydi")  # masalan "0 0 31 2 *"
    return value


def _history_start(value: str) -> str:
    # M1: kelajak sanasi bo'sh oyna beradi; 2015 dan oldin ma'lumot yo'q.
    parsed = date.fromisoformat(value)
    if not date(2015, 1, 1) <= parsed <= today_tashkent():
        raise ValueError("etl.history_start: 2015-01-01 va bugun oralig'ida bo'lishi kerak")
    return parsed.isoformat()


def int_def(key: str, default: int, lo: int, hi: int, **kw: Any) -> SettingDef:
    adapter: TypeAdapter[Any] = TypeAdapter(Annotated[int, Field(strict=True, ge=lo, le=hi)])
    return SettingDef(key, default, adapter, "int", lo=lo, hi=hi, **kw)


def float_def(key: str, default: float, lo: float, hi: float, **kw: Any) -> SettingDef:
    adapter: TypeAdapter[Any] = TypeAdapter(
        Annotated[float, Field(strict=True, ge=lo, le=hi, allow_inf_nan=False)])
    return SettingDef(key, default, adapter, "float", lo=lo, hi=hi, **kw)


def bool_def(key: str, default: bool, **kw: Any) -> SettingDef:
    return SettingDef(key, default, TypeAdapter(Annotated[bool, Field(strict=True)]), "bool", **kw)


def cron_def(key: str, default: str, **kw: Any) -> SettingDef:
    adapter: TypeAdapter[Any] = TypeAdapter(Annotated[str, Field(strict=True, max_length=64),
                                    AfterValidator(check_cron)])
    return SettingDef(key, default, adapter, "cron", **kw)


def str_def(key: str, default: str, pattern: str, max_length: int, **kw: Any) -> SettingDef:
    adapter: TypeAdapter[Any] = TypeAdapter(Annotated[str, Field(strict=True, pattern=pattern,
                                               max_length=max_length)])
    return SettingDef(key, default, adapter, "str", **kw)


_SEC: dict[str, Any] = {"category": "security", "perm": Perm.ADMIN_SECURITY, "guarded": True}
_SMTP: dict[str, Any] = {"category": "integrations", "perm": Perm.ADMIN_INTEGRATIONS,
                         "guarded": True}
_EMAILS: TypeAdapter[Any] = TypeAdapter(Annotated[
    list[Annotated[str, Field(strict=True, pattern=EMAIL_RE, max_length=254)]],
    Field(max_length=20)])

_DEFS: tuple[SettingDef, ...] = (
    # Витрина va ETL (2-reja kalitlari — nomlar va chegaralar o'zgarmagan)
    int_def("freshness.max_age_hours", 6, 1, 168, category="data",
            title="Порог устаревания данных витрины", unit="ч"),
    SettingDef("etl.history_start", "2024-01-01",
               TypeAdapter(Annotated[str, AfterValidator(_history_start)]), "date",
               category="etl", title="Начало истории загрузки", apply="next_run"),
    cron_def("etl.synthetic_cron", "0 2 * * *", category="etl",
             title="Расписание синтетической загрузки (только dev)"),
    int_def("builds.keep", 3, 2, 10, category="data", title="Хранить сборок витрины",
            apply="next_run"),
    int_def("partitions.months_ahead", 3, 1, 12, category="data",
            title="Создавать партиции наперёд", unit="мес.", apply="next_run"),
    cron_def("maintenance.partitions_cron", "30 3 * * *", category="etl",
             title="Обслуживание партиций"),
    cron_def("maintenance.cleanup_cron", "0 4 * * *", category="etl",
             title="Очистка сеансов и промежуточных данных"),
    int_def("etl.incremental_lookback_days", 45, 7, 120, category="etl",
            title="Окно инкрементальной загрузки", unit="дн.", apply="next_run"),
    # Sifat va saqlash
    float_def("quality.control_tolerance", 0.001, 0.0, 0.01, category="quality",
              title="Допуск сверки контрольных сумм (доля)", guarded=True, apply="next_run"),
    float_def("quality.balance_tolerance", 0.01, 0.0, 1.0, category="quality",
              title="Допуск баланса остатков (доля оборота)", guarded=True, apply="next_run"),
    int_def("retention.fact_years", 5, 5, 10, category="retention",
            title="Хранение фактов витрины", unit="лет", guarded=True, apply="next_run"),
    int_def("retention.audit_months", 12, 12, 120, category="retention",
            title="Хранение журнала аудита", unit="мес.", perm=Perm.ADMIN_SECURITY,
            guarded=True, apply="next_run"),
    SettingDef("notify.email_to", [], _EMAILS, "list", category="notify",
               title="Получатели оповещений (e-mail)", guarded=True, env="smtp_to",
               env_attr="smtp_recipients"),
    # Xavfsizlik siyosati: zaif chegara = hujjatlashtirilgan qiymat (faqat qattiqlashtirish)
    int_def("security.session_idle_minutes", 30, 5, 30, title="Завершение сеанса при бездействии",
            unit="мин", **_SEC),
    int_def("security.session_absolute_hours", 12, 1, 12, title="Максимальная длительность сеанса",
            unit="ч", **_SEC),
    int_def("security.password_max_age_days", 90, 30, 90, title="Срок действия пароля",
            unit="дн.", **_SEC),
    int_def("security.login_max_failures", 5, 3, 5,
            title="Неудачных попыток входа до блокировки", **_SEC),
    int_def("security.login_lockout_minutes", 15, 15, 1440, title="Длительность блокировки",
            unit="мин", **_SEC),
    int_def("security.password_min_length", 12, 12, 64, title="Минимальная длина пароля",
            unit="симв.", **_SEC),
    int_def("security.password_history", 5, 5, 24,
            title="Запрет повторного использования паролей", unit="посл.", **_SEC),
    # Buyurtmachi qarori 27.10.2026: 2FA majburiy emas. Bool uchun "pol" yo'q: yoqish ham,
    # o'chirish ham panel orqali (sabab + TOTP). Yoqilgan qiymat KEYINGI kirishda kuchga kiradi.
    bool_def("security.mfa_required", False, title="Обязательная двухфакторная аутентификация",
             **_SEC),
    int_def("ratelimit.login_per_min", 10, 3, 10, title="Попыток входа с одного IP в минуту",
            **_SEC),
    int_def("ratelimit.mfa_per_min", 20, 5, 20, title="Проверок кода 2FA с одного IP в минуту",
            **_SEC),
    int_def("ratelimit.api_per_min", 300, 60, 300,
            title="Запросов API одного пользователя в минуту", **_SEC),
    int_def("ratelimit.password_change_per_15min", 5, 1, 5,
            title="Попыток смены пароля за 15 минут", **_SEC),
    int_def("ops.restore_max_age_days", 40, 1, 40, category="ops", perm=Perm.ADMIN_SECURITY,
            guarded=True, title="Проверка восстановления не реже, чем раз в", unit="дн."),
    int_def("ops.dek_max_age_days", 365, 30, 365, category="ops", perm=Perm.ADMIN_SECURITY,
            guarded=True, title="Предупреждать о ротации ключа старше", unit="дн."),
    int_def("ops.clock_skew_max_seconds", 60, 5, 60, category="ops", perm=Perm.ADMIN_SECURITY,
            guarded=True, title="Допустимое расхождение часов", unit="с"),
    int_def("ops.tls_warn_days", 30, 30, 90, category="ops", perm=Perm.ADMIN_SECURITY,
            guarded=True, title="Предупреждать об истечении TLS-сертификата за", unit="дн."),
    int_def("ops.tls_critical_days", 7, 7, 30, category="ops", perm=Perm.ADMIN_SECURITY,
            guarded=True, title="Критично при истечении TLS-сертификата за", unit="дн."),
    # SMTP (integratsiya maydonlari — faqat /admin/integrations orqali o'zgaradi)
    str_def("smtp.host", "", r"^[A-Za-z0-9.-]{0,253}$", 253, title="Сервер SMTP",
            env="smtp_host", **_SMTP),
    int_def("smtp.port", 25, 1, 65535, title="Порт", env="smtp_port", **_SMTP),
    str_def("smtp.from", "ugekazna@localhost", r"^[^\s,<>@]+@[^\s,<>@]+$", 254,
            title="Адрес отправителя", env="smtp_from", **_SMTP),
    str_def("smtp.user", "", r"^[\x21-\x7e]{0,128}$", 128, title="Учётная запись",
            env="smtp_user", **_SMTP),
    bool_def("smtp.starttls", True, title="STARTTLS", env="smtp_starttls", **_SMTP),
    bool_def("smtp.ssl", False, title="SSL/TLS (SMTPS)", env="smtp_ssl", **_SMTP),
)
REGISTRY: dict[str, SettingDef] = {d.key: d for d in _DEFS}


def _plain(value: Any) -> Any:
    return value.get_secret_value() if isinstance(value, SecretStr) else value


def _try(d: SettingDef, raw: Any, source: Source) -> tuple[Any, Source] | None:
    try:
        return d.validate(raw), source
    except ValueError:
        log.error("setting_invalid", key=d.key, source=source)
        return None


def resolve(d: SettingDef, panel: dict[str, Any]) -> tuple[Any, Source]:
    if d.key in panel and (hit := _try(d, panel[d.key], "panel")) is not None:
        return hit
    if d.env is not None:
        settings = get_settings()
        source: Source = "env" if d.env in settings.model_fields_set else "default"
        if (hit := _try(d, _plain(getattr(settings, d.env_attr or d.env)), source)) is not None:
            return hit
    return d.default, "default"


def panel_rows(conn: Connection | Session) -> dict[str, Any]:
    rows = conn.execute(text("SELECT key, value FROM core.settings WHERE is_current")).all()
    return {r.key: r.value for r in rows if r.key in REGISTRY}


def current(conn: Connection | Session, key: str) -> Any:
    """Tranzaksiya ichida, keshsiz (ETL, worker joblari, CLI)."""
    d = REGISTRY[key]
    row = conn.execute(text("SELECT value FROM core.settings WHERE key = :k AND is_current"),
                       {"k": key}).first()
    return resolve(d, {} if row is None else {key: row.value})[0]


_lock = threading.Lock()
_cache: tuple[float, dict[str, Any]] | None = None


def _refresh(now: float) -> dict[str, Any]:
    global _cache
    try:
        with get_engine("app").connect() as conn:
            panel = panel_rows(conn)
    except SQLAlchemyError as exc:
        log.warning("settings_unavailable", error=type(exc).__name__)
        # Oxirgi qiymatlar (yoki hujjatlashtirilgan standartlar); TTL'dan keyin qayta urinadi.
        values = _cache[1] if _cache is not None else {
            k: resolve(d, {})[0] for k, d in REGISTRY.items()}
    else:
        values = {k: resolve(d, panel)[0] for k, d in REGISTRY.items()}
    _cache = (now, values)
    return values


def value(key: str) -> Any:
    """Keshlangan qiymat (≤ CACHE_TTL eskirgan) — har so'rovdagi issiq yo'l."""
    if key not in REGISTRY:
        raise KeyError(key)
    now = time.monotonic()
    cached = _cache
    if cached is not None and now - cached[0] < CACHE_TTL:
        return cached[1][key]
    with _lock:
        cached = _cache
        if cached is not None and now - cached[0] < CACHE_TTL:
            return cached[1][key]
        return _refresh(now)[key]


def invalidate() -> None:
    global _cache
    with _lock:
        _cache = None
