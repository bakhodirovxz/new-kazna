"""Tizim sozlamalari, «Требует внимания» qoidalari va финмодель допущения (spec 4.8, TZ 4).

Seed idempotent: faqat yo'q kalitlar qo'shiladi, administrator o'zgartirgan qiymatlarga
tegilmaydi. Chegaralar va допущения — TZ ochiq savoli: mijoz tasdiqlagach admin panelda
yangilanadi (har o'zgarish yangi versiya + audit).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from apscheduler.triggers.cron import CronTrigger
from pydantic import AfterValidator, Field, TypeAdapter
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import text
from sqlalchemy.engine import Connection


def _cron(value: str) -> str:
    # A4.2: aniq timezone="UTC" — tzlocal qidiruvisiz (filterwarnings = error::DeprecationWarning
    # ostida import/validate vaqtida DeprecationWarning'dan qochish uchun). Worker aniq TASHKENT
    # timezone bilan rejalashtiradi — bu yerda faqat sintaksis tekshiriladi.
    CronTrigger.from_crontab(value, timezone="UTC")  # noto'g'ri bo'lsa ValueError
    return value


def _iso_date(value: str) -> str:
    return date.fromisoformat(value).isoformat()


DEFAULT_SETTINGS: dict[str, Any] = {
    "freshness.max_age_hours": 6,
    "etl.history_start": "2024-01-01",
    "etl.synthetic_cron": "0 2 * * *",
    "builds.keep": 3,
    "retention.fact_years": 5,
    "retention.audit_months": 12,
    "partitions.months_ahead": 3,
}

SETTING_TYPES: dict[str, TypeAdapter[Any]] = {
    "freshness.max_age_hours": TypeAdapter(Annotated[int, Field(strict=True, ge=1, le=168)]),
    "etl.history_start": TypeAdapter(Annotated[str, AfterValidator(_iso_date)]),
    "etl.synthetic_cron": TypeAdapter(Annotated[str, AfterValidator(_cron)]),
    "builds.keep": TypeAdapter(Annotated[int, Field(strict=True, ge=2, le=10)]),
    "retention.fact_years": TypeAdapter(Annotated[int, Field(strict=True, ge=1, le=10)]),
    "retention.audit_months": TypeAdapter(Annotated[int, Field(strict=True, ge=12, le=120)]),
    "partitions.months_ahead": TypeAdapter(Annotated[int, Field(strict=True, ge=1, le=12)]),
}


def validate_setting(key: str, value: Any) -> Any:
    adapter = SETTING_TYPES[key]  # noma'lum kalit → KeyError
    try:
        return adapter.validate_python(value)
    except PydanticValidationError as exc:
        raise ValueError(f"{key}: noto'g'ri qiymat") from exc


@dataclass(frozen=True, slots=True)
class AlertRuleSeed:
    code: str
    title: str
    section: str
    page: str
    level: str
    threshold: dict[str, Any]


def _t(metric: str, op: str, value: float | int, **extra: str) -> dict[str, Any]:
    return {"metric": metric, "op": op, "value": value, **extra}


# TZ 4-bo'lim, «Панель „Требует внимания“» jadvali — 20 qoida, aynan shu chegaralar.
ALERT_RULES: tuple[AlertRuleSeed, ...] = (
    AlertRuleSeed("cash_below_monthly_outflow", "Остаток ниже месячного расходования", "kazna",
                  "svod", "critical", _t("balance_to_avg_monthly_outflow", "<", 1.0)),
    AlertRuleSeed("payments_14d_exceed_balance", "Платежи 14 дней превышают остаток", "kazna",
                  "calendar", "critical", _t("calendar_14d_to_balance", ">", 1.0)),
    AlertRuleSeed("payment_plan_execution", "Исполнение плана платежей", "kazna", "platezhi",
                  "warning", _t("payment_plan_execution", "<", 0.9)),
    AlertRuleSeed("contracts_overdue_90d", "Просроченные договоры", "kazna", "dogovory",
                  "critical", _t("contract_overdue_days", ">", 90)),
    AlertRuleSeed("overdue_payables_share", "Просроченная кредиторская задолженность", "kazna",
                  "dogovory", "warning", _t("overdue_payables_share", ">", 0.2)),
    AlertRuleSeed("loan_payments_30d", "Платежи по кредитам", "kredity", "grafik", "warning",
                  _t("loan_payment_days_ahead", "<=", 30)),
    AlertRuleSeed("fx_loans_share", "Доля валютных кредитов", "kredity", "svod", "warning",
                  _t("fx_loans_share", ">", 0.85)),
    AlertRuleSeed("procurement_overdue_lots", "Просроченные лоты закупок", "zakupki", "loty",
                  "critical", _t("overdue_lots_count", ">", 3)),
    AlertRuleSeed("direct_contracts_share", "Доля прямых договоров", "zakupki", "postavshiki",
                  "warning", _t("direct_contracts_share", ">", 0.25)),
    AlertRuleSeed("procurement_plan", "План закупок", "zakupki", "svod", "warning",
                  _t("procurement_plan_execution", "<", 0.6)),
    AlertRuleSeed("stock_below_minimum", "Позиции ниже минимума", "sklad", "minimum",
                  "critical", _t("below_min_positions", ">", 5)),
    AlertRuleSeed("illiquid_stock_share", "Неликвиды", "sklad", "nelikvid", "warning",
                  _t("illiquid_share", ">", 0.2)),
    AlertRuleSeed("generation_plan", "Выполнение плана выработки", "proizvodstvo", "stancii",
                  "warning", _t("generation_plan_execution", "<", 0.95, per="station")),
    AlertRuleSeed("energy_payment_level", "Уровень оплаты за энергию", "proizvodstvo",
                  "realiz", "warning", _t("energy_payment_level", "<", 0.85)),
    AlertRuleSeed("investment_schedule", "Адресная программа", "investicii", "svod", "warning",
                  _t("investment_schedule_execution", "<", 0.9)),
    AlertRuleSeed("fin_phys_gap", "Разрыв финансового и физического выполнения", "investicii",
                  "riski", "warning", _t("fin_phys_gap_pp", ">", 20)),
    AlertRuleSeed("advances_90d", "Незакрытые авансы", "investicii", "riski", "warning",
                  _t("advance_age_days", ">", 90)),
    AlertRuleSeed("vacancies_share", "Вакансии", "kadry", "chislennost", "warning",
                  _t("vacancy_share", ">", 0.1)),
    AlertRuleSeed("turnover", "Текучесть", "kadry", "dvizhenie", "warning",
                  _t("turnover_rate", ">", 0.08)),
    AlertRuleSeed("overtime", "Сверхурочные", "kadry", "dvizhenie", "warning",
                  _t("overtime_hours_per_employee", ">", 20)),
)

SCENARIOS = ("base", "water", "tariff", "fx")
SCENARIO_TITLES = {
    "base": "Базовый",
    "water": "Маловодье",
    "tariff": "Сдержанный тариф",
    "fx": "Ослабление сума",
}
FIN_YEARS = range(2026, 2033)
FIN_KEYS = ("tariff_growth", "generation_factor", "fx_rate_factor", "opex_index", "tax_rate",
            "kium")
# Bazaviy допущения — vaqtinchalik (TZ ochiq savoli), mijoz tasdiqlagach yangilanadi.
_BASE = {
    "tariff_growth": Decimal("0.08"),
    "generation_factor": Decimal("1"),
    "fx_rate_factor": Decimal("1"),
    "opex_index": Decimal("0.07"),
    "tax_rate": Decimal("0.15"),
    "kium": Decimal("0.40"),
}


def fin_assumption_seeds() -> list[tuple[str, int, str, Decimal]]:
    rows: list[tuple[str, int, str, Decimal]] = []
    for scenario in SCENARIOS:
        for year in FIN_YEARS:
            for key in FIN_KEYS:
                value = _BASE[key]
                if scenario == "water" and key == "generation_factor" and 2027 <= year <= 2029:
                    value = Decimal("0.85")  # маловодье: выработка −15% в 2027–2029
                if scenario == "tariff" and key == "tariff_growth":
                    value = Decimal("0.04")  # рост тарифа 4% вместо 8%
                if scenario == "fx" and key == "fx_rate_factor":
                    value = Decimal("1.2")  # курс +20%
                rows.append((scenario, year, key, value))
    return rows


def ensure_reference(conn: Connection) -> None:
    """Bootstrap'da chaqiriladi (ugk_app). Faqat yo'q yozuvlarni qo'shadi.

    `core.data_version`ning yagona qatori (`id = 1`) bu yerda ENDI seed qilinmaydi — fix r1
    (M1): u 0007 migratsiyasida bir marta yoziladi va `ugk_app`da bu jadvalga endi INSERT
    huquqi yo'q (faqat `active_build_id`/`published_at` ustunlariga ustun darajasidagi
    UPDATE) — least privilege. Testlarda qator `_reset_core()` TRUNCATE'idan keyin
    `ugk_migrator` ulanishi bilan qayta seed qilinadi (`tests/conftest.py`).
    """
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('ugk_reference'))"))
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute(
            text(
                # Fix (brief demonstrably broken under psycopg3): :k reused untyped in the
                # SELECT target-list AND compared to a varchar column in WHERE makes the
                # planner deduce conflicting types (text vs character varying) for the same
                # placeholder — psycopg raises AmbiguousParameter. An explicit CAST on the
                # first occurrence fixes type resolution for all occurrences of :k.
                "INSERT INTO core.settings (key, version, value) "
                "SELECT CAST(:k AS varchar(64)), 1, CAST(:v AS jsonb) "
                "WHERE NOT EXISTS (SELECT 1 FROM core.settings WHERE key = :k)"
            ),
            {"k": key, "v": json.dumps(value)},
        )
    for rule in ALERT_RULES:
        conn.execute(
            text(
                "INSERT INTO core.alert_rules (code, version, title, section, page, threshold, "
                "level) SELECT CAST(:c AS varchar(64)), 1, :t, :s, :p, CAST(:th AS jsonb), :l "
                "WHERE NOT EXISTS (SELECT 1 FROM core.alert_rules WHERE code = :c)"
            ),
            {"c": rule.code, "t": rule.title, "s": rule.section, "p": rule.page,
             "th": json.dumps(rule.threshold), "l": rule.level},
        )
    conn.execute(
        text(
            "INSERT INTO core.fin_assumptions (scenario, year, key, version, value) "
            "SELECT CAST(:s AS varchar(8)), :y, CAST(:k AS varchar(64)), 1, :v "
            "WHERE NOT EXISTS (SELECT 1 FROM core.fin_assumptions "
            "WHERE scenario = :s AND year = :y AND key = :k)"
        ),
        [{"s": s, "y": y, "k": k, "v": v} for s, y, k, v in fin_assumption_seeds()],
    )


def current_setting(conn: Connection, key: str) -> Any:
    if key not in DEFAULT_SETTINGS:
        raise KeyError(key)
    value = conn.execute(
        text("SELECT value FROM core.settings WHERE key = :k AND is_current"), {"k": key}
    ).scalar_one_or_none()
    return DEFAULT_SETTINGS[key] if value is None else value
