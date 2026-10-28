"""Финмодель 2026–2032 — sof hisob (TZ 4 «Финансовая модель», S5 spec 3.1).

DB, vaqt va tarmoqqa bog'liq emas: kirish — витрина faktlaridan yig'ilgan `FinInputs` va
bitta ssenariy допущения'lari (`ScenarioAssumptions`), chiqish — yillar bo'yicha `YearRow`.
Hisob Decimal'da; yaxlitlash faqat saqlashda (mart ustunlari) bajariladi.

Birliklar: pul — mln so'm; quvvat — MVt; ishlab chiqarish/отпуск — mln kVt·soat; tarif va
tannarx — so'm/kVt·soat; ulushlar — 0..1.
"""

from __future__ import annotations

import calendar
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal(0)
ONE = Decimal(1)
THOUSAND = Decimal(1000)


@dataclass(frozen=True, slots=True)
class YearAssumptions:
    tariff_growth: Decimal  # tarif o'sishi (ikkinchi model yilidan)
    generation_factor: Decimal  # ishlab chiqarish koeffitsienti (маловодье: 0,85)
    fx_rate_factor: Decimal  # kurs koeffitsienti (ослабление сума: 1,2)
    opex_index: Decimal  # operatsion xarajatlar o'sishi (ikkinchi model yilidan)
    tax_rate: Decimal  # soliqlar va majburiy to'lovlar — tushumdan ulush
    kium: Decimal  # КИУМ
    capacity_add_mw: Decimal  # АИП bo'yicha yil ichida ishga tushadigan quvvat


@dataclass(frozen=True, slots=True)
class ScalarAssumptions:
    tariff_start: Decimal  # birinchi model yilining tarifi, so'm/kVt·soat
    own_needs_share: Decimal  # o'z ehtiyojlari ulushi (отпуск = выработка × (1 − ulush))
    capex_fx_share: Decimal  # investitsiyalarning valyutali qismi (kurs tuzatmasi uchun)


@dataclass(frozen=True, slots=True)
class ScenarioAssumptions:
    years: Mapping[int, YearAssumptions]
    scalars: ScalarAssumptions


@dataclass(frozen=True, slots=True)
class DebtYear:
    """Kredit grafigi bir yil uchun, so'mda (valyuta qismi — `as_of` kursida)."""

    uzs_principal: Decimal = ZERO
    uzs_interest: Decimal = ZERO
    fx_principal: Decimal = ZERO
    fx_interest: Decimal = ZERO


NO_DEBT = DebtYear()


@dataclass(frozen=True, slots=True)
class FinInputs:
    """Витрина faktlari (build sanasi `as_of` holatiga)."""

    capacity_mw: Decimal  # o'rnatilgan quvvat (stansiyalar yig'indisi)
    opex_base: Decimal  # operatsion xarajatlar: oxirgi 12 yopilgan oy (soliq/kreditsiz)
    opening_cash: Decimal  # hisoblardagi qoldiq
    aip_plan: Mapping[int, Decimal]  # АИП rejasi yillar bo'yicha
    debt: Mapping[int, DebtYear]


@dataclass(frozen=True, slots=True)
class YearRow:
    year: int
    capacity_mw: Decimal
    generation: Decimal
    supply: Decimal
    tariff: Decimal
    revenue: Decimal
    opex: Decimal
    tax: Decimal
    ebitda: Decimal
    margin: Decimal | None
    capex_plan: Decimal
    capex: Decimal
    principal: Decimal
    interest: Decimal
    debt_service: Decimal
    net_flow: Decimal
    balance: Decimal
    dscr: Decimal | None
    covenant_breach: bool
    unit_cost: Decimal | None


def year_hours(year: int) -> Decimal:
    """«Часы года» — kalendar soatlari (kabisa yili 8784)."""
    return Decimal((366 if calendar.isleap(year) else 365) * 24)


def run_model(inputs: FinInputs, scenario: ScenarioAssumptions, *,
              covenant: Decimal) -> list[YearRow]:
    """TZ 4 formulalari; yillar — `scenario.years` kalitlari o'sish tartibida."""
    rows: list[YearRow] = []
    s = scenario.scalars
    capacity = inputs.capacity_mw
    balance = inputs.opening_cash
    tariff = s.tariff_start
    opex = inputs.opex_base
    for index, year in enumerate(sorted(scenario.years)):
        a = scenario.years[year]
        capacity += a.capacity_add_mw  # мощность года = предыдущего + ввод по АИП
        if index:
            tariff *= ONE + a.tariff_growth
            opex *= ONE + a.opex_index  # база текущего года × индекс роста
        generation = capacity * year_hours(year) * a.kium * a.generation_factor / THOUSAND
        supply = generation * (ONE - s.own_needs_share)
        revenue = supply * tariff
        tax = revenue * a.tax_rate
        ebitda = revenue - opex - tax
        capex_plan = inputs.aip_plan.get(year, ZERO)
        capex = capex_plan * (ONE + (a.fx_rate_factor - ONE) * s.capex_fx_share)
        debt = inputs.debt.get(year, NO_DEBT)
        principal = debt.uzs_principal + debt.fx_principal * a.fx_rate_factor
        interest = debt.uzs_interest + debt.fx_interest * a.fx_rate_factor
        service = principal + interest
        net = ebitda - capex - service
        balance += net
        dscr = ebitda / service if service > ZERO else None
        rows.append(YearRow(
            year=year, capacity_mw=capacity, generation=generation, supply=supply,
            tariff=tariff, revenue=revenue, opex=opex, tax=tax, ebitda=ebitda,
            margin=ebitda / revenue if revenue else None, capex_plan=capex_plan, capex=capex,
            principal=principal, interest=interest, debt_service=service, net_flow=net,
            balance=balance, dscr=dscr, covenant_breach=dscr is not None and dscr < covenant,
            unit_cost=(opex + tax) / supply if supply > ZERO else None))
    return rows
