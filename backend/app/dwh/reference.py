"""Sozlama taxalluslari, «Требует внимания» qoidalari va финмодель допущения (spec 4.8, TZ 4).

Seed idempotent: faqat yo'q alert qoidalari va допущения qo'shiladi (sozlamalar seed qilinmaydi).
Chegaralar va допущения — TZ ochiq savoli: mijoz tasdiqlagach admin panelda yangilanadi
(har o'zgarish yangi versiya + audit).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core import sysconfig
from app.core.setting_types import CALENDAR_KINDS, OneCOrg  # noqa: F401  (S1 importlari)
from app.core.sysconfig import REGISTRY

# Taxalluslar: yagona manba — app/core/sysconfig.py reyestri (04b).
DEFAULT_SETTINGS: dict[str, Any] = {k: d.default for k, d in REGISTRY.items()}
SETTING_TYPES: dict[str, TypeAdapter[Any]] = {k: d.adapter for k, d in REGISTRY.items()}


# S1–S5 rejalari `_cron` va `current_setting` nomlarini shu moduldan import qiladi.
_cron = sysconfig.check_cron
current_setting = sysconfig.current


def validate_setting(key: str, value: Any) -> Any:
    return REGISTRY[key].validate(value)  # noma'lum kalit → KeyError


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
FIN_FIRST_YEAR = FIN_YEARS[0]
FIN_YEAR_KEYS = ("tariff_growth", "generation_factor", "fx_rate_factor", "opex_index", "tax_rate",
                 "kium", "capacity_add_mw")
# S5: skalyar допущения — faqat model birinchi yili (FIN_FIRST_YEAR) qatorida saqlanadi.
FIN_SCALAR_KEYS = ("tariff_start", "own_needs_share", "capex_fx_share")
FIN_KEYS = FIN_YEAR_KEYS + FIN_SCALAR_KEYS
# Har kalit uchun ruxsat etilgan oraliq (admin API tekshiradi; umumiy ±10 o'rniga).
FIN_KEY_BOUNDS: dict[str, tuple[Decimal, Decimal]] = {
    "tariff_growth": (Decimal("-0.5"), Decimal("1")),
    "generation_factor": (Decimal("0"), Decimal("2")),
    "fx_rate_factor": (Decimal("0.1"), Decimal("5")),
    "opex_index": (Decimal("-0.5"), Decimal("1")),
    "tax_rate": (Decimal("0"), Decimal("0.9")),
    "kium": (Decimal("0.01"), Decimal("1")),
    "capacity_add_mw": (Decimal("0"), Decimal("5000")),
    "tariff_start": (Decimal("1"), Decimal("100000")),
    "own_needs_share": (Decimal("0"), Decimal("0.5")),
    "capex_fx_share": (Decimal("0"), Decimal("1")),
}
# Bazaviy допущения — vaqtinchalik (TZ ochiq savoli), mijoz tasdiqlagach yangilanadi.
_BASE = {
    "tariff_growth": Decimal("0.08"),
    "generation_factor": Decimal("1"),
    "fx_rate_factor": Decimal("1"),
    "opex_index": Decimal("0.07"),
    "tax_rate": Decimal("0.15"),
    "kium": Decimal("0.40"),
    "tariff_start": Decimal("705"),  # prototip: 2026 tarifi, so'm/kVt·soat
    "own_needs_share": Decimal("0.016"),  # prototip ownSh
    "capex_fx_share": Decimal("0.4"),  # prototip: investitsiyalarning valyutali qismi
}
# Prototip addCap: АИП bo'yicha ввод мощностей, MVt (2026 — joriy yil, quvvat allaqachon hisobda).
_CAPACITY_ADD = {2026: 0, 2027: 120, 2028: 210, 2029: 95, 2030: 60, 2031: 40, 2032: 30}


def fin_value_error(year: int, key: str, value: Decimal) -> str | None:
    """Admin API tekshiruvi: noma'lum kalit, skalyar kalit noto'g'ri yilda, chegaradan tashqari."""
    if key not in FIN_KEY_BOUNDS:
        return "key"
    if key in FIN_SCALAR_KEYS and year != FIN_FIRST_YEAR:
        return "year"
    low, high = FIN_KEY_BOUNDS[key]
    if not value.is_finite() or not low <= value <= high:
        return "value"
    return None


def fin_assumption_seeds() -> list[tuple[str, int, str, Decimal]]:
    rows: list[tuple[str, int, str, Decimal]] = []
    for scenario in SCENARIOS:
        for year in FIN_YEARS:
            for key in FIN_YEAR_KEYS:
                value = Decimal(_CAPACITY_ADD[year]) if key == "capacity_add_mw" else _BASE[key]
                if scenario == "water" and key == "generation_factor" and 2027 <= year <= 2029:
                    value = Decimal("0.85")  # маловодье: выработка −15% в 2027–2029
                if scenario == "tariff" and key == "tariff_growth":
                    value = Decimal("0.04")  # рост тарифа 4% вместо 8%
                if scenario == "fx" and key == "fx_rate_factor":
                    value = Decimal("1.2")  # курс +20%
                rows.append((scenario, year, key, value))
            if year == FIN_FIRST_YEAR:
                rows.extend((scenario, year, key, _BASE[key]) for key in FIN_SCALAR_KEYS)
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
