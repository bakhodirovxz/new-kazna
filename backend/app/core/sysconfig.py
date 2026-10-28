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
from app.core.setting_types import (
    BANKS,
    DEFAULT_METHOD_NORMS,
    AskueStation,
    BankAccount,
    HrOrg,
    OneCOrg,
    askue_stations,
    bank_accounts,
    bank_formats,
    branch_codes,
    calendar_kinds,
    currencies,
    external_base_url,
    hr_orgs,
    method_norms,
    onec_orgs,
    onec_url_host,
)
from app.dwh.dates import today_tashkent

Kind = Literal["int", "float", "bool", "str", "cron", "date", "list", "json"]
Apply = Literal["live", "next_run"]
Source = Literal["panel", "env", "default"]
KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
ONEC_URL_RE = r"^(https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~/-]*)?)?$"
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
_CHAT_IDS: TypeAdapter[Any] = TypeAdapter(Annotated[
    list[Annotated[str, Field(strict=True, pattern=r"^-?[0-9]{1,20}$")]],
    Field(max_length=10)])
_AI: dict[str, Any] = {"category": "ai", "perm": Perm.ADMIN_SECURITY, "guarded": True}
_AIINT: dict[str, Any] = {"category": "integrations", "perm": Perm.ADMIN_INTEGRATIONS,
                          "guarded": True}
_EMAILS: TypeAdapter[Any] = TypeAdapter(Annotated[
    list[Annotated[str, Field(strict=True, pattern=EMAIL_RE, max_length=254)]],
    Field(max_length=20)])

def _unique_codes(value: list[str]) -> list[str]:
    if len(set(value)) != len(value):
        raise ValueError("takrorlangan statya kodi")
    return value


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
    # S1: kalendar turlari va 1C (kodda emas, panelda)
    SettingDef("kazna.calendar_kinds",
               {"taxes": ["PKM54-O03"], "salary": ["PKM54-O05"], "loans": ["PKM54-O04"]},
               TypeAdapter(Annotated[dict[str, list[str]], AfterValidator(calendar_kinds)]),
               "json", category="kazna", title="Статьи платёжного календаря", apply="next_run"),
    SettingDef("onec.orgs", [],
               TypeAdapter(Annotated[list[OneCOrg], AfterValidator(onec_orgs)]), "json",
               category="onec", title="Организации 1С и филиалы", apply="next_run"),
    bool_def("onec.income_enabled", False, category="onec",
             title="Загружать поступления (/income)", apply="next_run"),
    int_def("onec.page_limit", 100000, 1000, 1_000_000, category="onec",
            title="Размер страницы запроса к 1С", unit="строк", apply="next_run"),
    cron_def("etl.onec_full_cron", "0 2 * * *", category="etl",
             title="Расписание полной загрузки 1С"),
    cron_def("etl.onec_incremental_cron", "0 10,13,16 * * *", category="etl",
             title="Расписание инкрементальной загрузки 1С"),
    # S2: banklar, kurslar, Telegram
    SettingDef("banks.accounts", [],
               TypeAdapter(Annotated[list[BankAccount], AfterValidator(bank_accounts)]), "json",
               category="banks", title="Банковские счета", apply="next_run",
               perm=Perm.ADMIN_INTEGRATIONS, guarded=True),
    SettingDef("banks.statement_branches", [],
               TypeAdapter(Annotated[list[str], AfterValidator(branch_codes)]), "list",
               category="banks", title="Филиалы с проводками из банковских выписок",
               apply="next_run", perm=Perm.ADMIN_INTEGRATIONS, guarded=True),
    SettingDef("banks.formats", dict.fromkeys(BANKS, "canonical"),
               TypeAdapter(Annotated[dict[str, str], AfterValidator(bank_formats)]), "json",
               category="banks", title="Форматы выписок банков", apply="next_run"),
    cron_def("etl.banks_cron", "30 9,12,15,18 * * *", category="banks",
             title="Расписание загрузки банковских выписок"),
    cron_def("etl.cbu_cron", "0 8 * * *", category="fx",
             title="Расписание загрузки курсов ЦБ РУз"),
    SettingDef("fx.currencies", ["USD", "EUR", "CNY", "RUB", "GBP", "JPY", "CHF", "KZT", "KRW"],
               TypeAdapter(Annotated[list[str], AfterValidator(currencies)]), "list",
               category="fx", title="Валюты курсов ЦБ", apply="next_run"),
    int_def("fx.lookback_days", 7, 1, 31, category="fx", title="Окно загрузки курсов",
            unit="дн.", apply="next_run"),
    cron_def("telegram.summary_cron", "30 8 * * *", category="notify",
             title="Расписание ежедневной сводки в Telegram"),
    # S4: xaridlar va kadrlar
    SettingDef("zakupki.method_norms", dict(DEFAULT_METHOD_NORMS),
               TypeAdapter(Annotated[dict[str, Annotated[int, Field(strict=True, ge=1, le=365)]],
                                     AfterValidator(method_norms)]),
               "json", category="zakupki", title="Нормативные сроки закупок по способам (дни)",
               apply="next_run"),
    SettingDef("hr.orgs", [], TypeAdapter(Annotated[list[HrOrg], AfterValidator(hr_orgs)]),
               "json", category="hr", title="Организации кадровой системы и филиалы",
               apply="next_run"),
    # k-anonimlik (TZ 9, shaxsiy ma'lumot): guruh < chegara bo'lsa ФОТ/o'rtacha/oqimlar yashiriladi.
    # Faqat qattiqlashtirish: 3 dan past bo'lmaydi, standart 5.
    int_def("kadry.min_group", 5, 3, 1000, category="hr",
            title="Минимальный размер группы для показа ФОТ и средней зарплаты", unit="чел.",
            guarded=True),
    cron_def("etl.hr_cron", "30 6 * * *", category="etl",
             title="Расписание загрузки кадровых данных"),
    cron_def("etl.onec_zakupki_cron", "40 2 * * *", category="etl",
             title="Расписание загрузки плана закупок 1С"),
    # S3: АСКУЭ, jonli quvvat va 1C ombori
    SettingDef("askue.stations", [],
               TypeAdapter(Annotated[list[AskueStation], AfterValidator(askue_stations)]),
               "json", category="askue", title="Станции АСКУЭ и филиалы", apply="next_run"),
    int_def("askue.inbox_days", 7, 1, 60, category="askue",
            title="Перечитывать выгрузки АСКУЭ за последние", unit="дн.", apply="next_run"),
    int_def("askue.live_keep_days", 35, 1, 400, category="askue",
            title="Хранить снимки текущей мощности", unit="дн.", apply="next_run"),
    int_def("askue.live_stale_minutes", 30, 5, 1440, category="askue",
            title="Снимок мощности устарел через", unit="мин"),
    cron_def("askue.live_cron", "*/10 * * * *", category="askue",
             title="Расписание опроса текущей мощности"),
    cron_def("etl.askue_cron", "15 7 * * *", category="etl",
             title="Расписание загрузки выгрузок АСКУЭ"),
    int_def("onec.sklad_months", 13, 1, 36, category="sklad",
            title="Глубина загрузки остатков склада 1С", unit="мес.", apply="next_run"),
    cron_def("etl.onec_sklad_full_cron", "30 3 * * *", category="etl",
             title="Расписание полной загрузки склада 1С"),
    cron_def("etl.onec_sklad_incremental_cron", "30 10,13,16 * * *", category="etl",
             title="Расписание инкрементальной загрузки склада 1С"),
    # S5: финмодель — ковенант va xarajat bazasidan chiqariladigan statyalar (masalan, 1C'da
    # «operating» deb kelgan kapital xarajat statyalari)
    float_def("finmodel.dscr_covenant", 1.2, 0.5, 5.0, category="finmodel",
              title="Ковенант DSCR (минимум)"),
    SettingDef("finmodel.opex_exclude_items", [],
               TypeAdapter(Annotated[
                   list[Annotated[str, Field(strict=True, min_length=1, max_length=64)]],
                   Field(max_length=200), AfterValidator(_unique_codes)]),
               "list", category="finmodel", title="Статьи, исключаемые из операционных расходов",
               apply="next_run"),
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
    int_def("ratelimit.data_write_per_min", 60, 10, 60,
            title="Записей ввода данных одного пользователя в минуту", **_SEC),
    str_def("manual.locked_through", "", r"^(\d{4}-(0[1-9]|1[0-2]))?$", 7, category="data",
            guarded=True, title="Ввод данных: закрыт период по (ГГГГ-ММ)"),
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
    # S3 integratsiya maydonlari (sirlar — integrations.py, faqat panel)
    str_def("askue.live_url", "", r"^(https://[A-Za-z0-9./_-]+)?$", 300,
            title="Адрес источника текущей мощности (https)", **_SMTP),
    str_def("onec_sklad.base_url", "", ONEC_URL_RE, 300,
            title="Адрес HTTP-сервиса 1С: склад", **_SMTP),
    # SMTP (integratsiya maydonlari — faqat /admin/integrations orqali o'zgaradi)
    str_def("smtp.host", "", r"^[A-Za-z0-9.-]{0,253}$", 253, title="Сервер SMTP",
            env="smtp_host", **_SMTP),
    int_def("smtp.port", 25, 1, 65535, title="Порт", env="smtp_port", **_SMTP),
    str_def("smtp.from", "ugekazna@localhost", r"^[^\s,<>@]+@[^\s,<>@]+$", 254,
            title="Адрес отправителя", env="smtp_from", **_SMTP),
    str_def("smtp.user", "", r"^[\x21-\x7e]{0,128}$", 128, title="Учётная запись",
            env="smtp_user", **_SMTP),
    bool_def("smtp.starttls", True, title="STARTTLS", env="smtp_starttls", **_SMTP),
    bool_def("cbu.enabled", False, title="Загружать курсы ЦБ РУз", **_SMTP),
    SettingDef("telegram.chat_ids", [], _CHAT_IDS, "list", title="Чаты Telegram", **_SMTP),
    # A-S2.R1: Telegram - tashqi bulut xizmati; sukut bo'yicha hech narsa yuborilmaydi (mijoz/CSC
    # yozma roziligigacha). org_totals - faqat tashkilot jami (filial/kontragent yo'q).
    SettingDef("telegram.summary_scope", "off",
               TypeAdapter(Literal["off", "org_totals"]), "str",
               title="Дневная сводка в Telegram (off — не отправлять)", **_SMTP),
    bool_def("telegram.forward_alerts", False,
             title="Пересылать в Telegram оповещения о сбоях (без сумм и названий)", **_SMTP),
    bool_def("smtp.ssl", False, title="SSL/TLS (SMTPS)", env="smtp_ssl", **_SMTP),
    # 1C HTTP-servislari (integratsiya maydonlari; login/parol — core.integrations sirlari)
    SettingDef("onec.base_url", "", TypeAdapter(Annotated[str, Field(
        strict=True, max_length=300,
        pattern=r"^(https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~/-]*)?)?$"),
        AfterValidator(onec_url_host)]), "str", title="Адрес HTTP-сервиса 1С", **_SMTP),
    int_def("onec.max_mb", 64, 1, 128, title="Максимальный размер ответа 1С", unit="МБ",
            **_SMTP),
    # HR API (S4): manzil faqat https; API-kalit — integrations siri `hr.api_key`
    SettingDef("hr.base_url", "https://hr-api.uzgidro.uz", TypeAdapter(Annotated[
        str, Field(strict=True, max_length=300,
                   pattern=r"^(https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~/-]*)?)?$"),
        AfterValidator(external_base_url)]), "str", title="Адрес кадровой системы (HR API)",
        **_SMTP),
    cron_def("hr.attendance_cron", "*/10 7-20 * * *", category="hr",
             title="Расписание опроса явки на сегодня"),
    cron_def("hr.attendance_nightly_cron", "20 1 * * *", category="hr",
             title="Расписание повторной загрузки явки за вчера"),
    int_def("hr.attendance_stale_minutes", 30, 5, 1440, category="hr",
            title="Данные о явке устарели через", unit="мин"),
    # S5: AI-анализ standart holatda O'CHIQ — yoqish infosec roziligidan keyin (sabab + TOTP).
    bool_def("ai.enabled", False, title="AI-анализ включён", **_AI),
    int_def("ai.user_per_hour", 20, 1, 1000, title="Запросов AI-анализа на пользователя в час",
            **_AI),
    int_def("ai.org_per_day", 300, 1, 100_000, title="Запросов AI-анализа на организацию в сутки",
            **_AI),
    str_def("ai.model", "claude-opus-5-5", r"^[a-z0-9.-]{1,64}$", 64, title="Модель AI", **_AIINT),
    SettingDef("ai.effort", "medium", TypeAdapter(Literal["low", "medium", "high"]), "str",
               title="Глубина рассуждения AI", **_AIINT),
    int_def("ai.max_tokens", 8000, 1000, 32000, title="Максимум токенов ответа AI", **_AIINT),
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
