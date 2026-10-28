"""«Финмодель» API javoblari (S5 spec 3.5)."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from typing import Literal

from app.dwh.reference import SCENARIO_TITLES
from app.finmodel.summary import FinYear, ScenarioSummary, Sensitivity
from app.sections.schemas import _Out

# Prototip SCEN[].d — ssenariy izohi (ssenariylar jadvali va almashtirgich ostida).
SCENARIO_NOTES = {
    "base": "Приток воды в норме, тариф растёт по плану, курс стабилен",
    "water": "Выработка ниже нормы на 15% в 2027–2029 годах",
    "tariff": "Тариф растёт на 4% в год вместо 8%",
    "fx": "Курс растёт на 20%: дорожают валютные кредиты и импортное оборудование",
}


class FinYearOut(_Out):
    year: int
    capacity_mw: float
    generation: float
    supply: float
    tariff: float
    revenue: float
    opex: float
    tax: float
    ebitda: float
    margin: float | None
    capex_plan: float
    capex: float
    principal: float
    interest: float
    debt_service: float
    net_flow: float
    balance: float
    dscr: float | None
    covenant_breach: bool
    unit_cost: float | None


class FinSummaryOut(_Out):
    scenario: str
    title: str
    note: str
    capacity_last: float
    capacity_added: float
    revenue_first: float
    revenue_last: float
    ebitda_total: float
    margin_avg: float | None
    capex_total: float
    debt_service_total: float
    dscr_min: float | None
    dscr_min_year: int | None
    cum_flow: float
    negative_years: int
    verdict: Literal["funded", "needs_financing"]


class FinSensitivityOut(_Out):
    scenario: str
    title: str
    delta_cum: float
    dscr_min: float | None


class FinBaseOut(_Out):
    as_of: date
    capacity_mw: float
    opex_base: float
    opex_months: int
    opening_cash: float
    missing_fx: list[str]
    aip_missing_years: list[int]
    assumptions_at: datetime | None
    stale_assumptions: bool
    covenant: float


class FinmodelOut(_Out):
    has_model: bool
    scenario: str
    company_wide: bool
    base: FinBaseOut | None
    years: list[FinYearOut]
    summary: FinSummaryOut | None
    scenarios: list[FinSummaryOut]
    sensitivity: list[FinSensitivityOut]


def year_out(y: FinYear) -> FinYearOut:
    return FinYearOut(**asdict(y))


def summary_out(s: ScenarioSummary) -> FinSummaryOut:
    return FinSummaryOut(**asdict(s), title=SCENARIO_TITLES[s.scenario],
                         note=SCENARIO_NOTES[s.scenario])


def sensitivity_out(x: Sensitivity) -> FinSensitivityOut:
    return FinSensitivityOut(scenario=x.scenario, title=SCENARIO_TITLES[x.scenario],
                             delta_cum=x.delta_cum, dscr_min=x.dscr_min)
