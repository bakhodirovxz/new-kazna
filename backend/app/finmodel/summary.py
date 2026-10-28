"""Ssenariy xulosasi, taqqoslash va sezgirlik — saqlangan yillik qatorlardan (so'rovda, arzon).

Kirish — `pub.agg_finmodel_year` qatorlari (float). Prototip `fin()`/`scenTable()` mantiqi:
«требует привлечения финансирования» — minimal DSCR ковенантдан past yoki jamg'arilgan oqim manfiy.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.finmodel.model import YearRow

Verdict = Literal["funded", "needs_financing"]
BASE = "base"


@dataclass(frozen=True, slots=True)
class FinYear:
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


@dataclass(frozen=True, slots=True)
class ScenarioSummary:
    scenario: str
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
    verdict: Verdict


@dataclass(frozen=True, slots=True)
class Sensitivity:
    scenario: str
    delta_cum: float
    dscr_min: float | None


def _opt(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def from_row(row: YearRow) -> FinYear:
    """Sof model natijasini float qatorga (testlar va saqlash tekshiruvi uchun)."""
    return FinYear(
        year=row.year, capacity_mw=float(row.capacity_mw), generation=float(row.generation),
        supply=float(row.supply), tariff=float(row.tariff), revenue=float(row.revenue),
        opex=float(row.opex), tax=float(row.tax), ebitda=float(row.ebitda),
        margin=_opt(row.margin), capex_plan=float(row.capex_plan), capex=float(row.capex),
        principal=float(row.principal), interest=float(row.interest),
        debt_service=float(row.debt_service), net_flow=float(row.net_flow),
        balance=float(row.balance), dscr=_opt(row.dscr), covenant_breach=row.covenant_breach,
        unit_cost=_opt(row.unit_cost))


def summarize(scenario: str, years: Sequence[FinYear], *, base_capacity: float,
              covenant: float) -> ScenarioSummary:
    if not years:
        raise ValueError("bo'sh ssenariy")
    ordered = sorted(years, key=lambda y: y.year)
    margins = [y.margin for y in ordered if y.margin is not None]
    with_dscr = [(y.dscr, y.year) for y in ordered if y.dscr is not None]
    worst = min(with_dscr) if with_dscr else None
    cum = sum(y.net_flow for y in ordered)
    dscr_min = None if worst is None else worst[0]
    bad = (dscr_min is not None and dscr_min < covenant) or cum < 0
    return ScenarioSummary(
        scenario=scenario, capacity_last=ordered[-1].capacity_mw,
        capacity_added=ordered[-1].capacity_mw - base_capacity,
        revenue_first=ordered[0].revenue, revenue_last=ordered[-1].revenue,
        ebitda_total=sum(y.ebitda for y in ordered),
        margin_avg=sum(margins) / len(margins) if margins else None,
        capex_total=sum(y.capex for y in ordered),
        debt_service_total=sum(y.debt_service for y in ordered),
        dscr_min=dscr_min, dscr_min_year=None if worst is None else worst[1],
        cum_flow=cum, negative_years=sum(1 for y in ordered if y.balance < 0),
        verdict="needs_financing" if bad else "funded")


def sensitivity(summaries: Mapping[str, ScenarioSummary]) -> list[Sensitivity]:
    """Jamg'arilgan oqimning bazaviy ssenariyga nisbatan o'zgarishi — kattasi birinchi."""
    base = summaries.get(BASE)
    if base is None:
        return []
    out = [Sensitivity(s.scenario, s.cum_flow - base.cum_flow, s.dscr_min)
           for s in summaries.values() if s.scenario != BASE]
    return sorted(out, key=lambda x: (-abs(x.delta_cum), x.scenario))
