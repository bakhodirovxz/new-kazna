"""Финмодель o'qish so'rovlari — faqat `pub.agg_finmodel_year` (aktiv build, RLS: scope_all)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session

from app.dwh.dates import from_date_id
from app.finmodel.summary import FinYear

_SQL = """
SELECT scenario, year, capacity_mw, generation, supply, tariff, revenue, opex, tax, ebitda,
       margin, capex_plan, capex, principal, interest, debt_service, net_flow, balance, dscr,
       covenant_breach, unit_cost, as_of_id, base_capacity_mw, opex_base, opex_months,
       opening_cash, missing_fx, assumptions_at, covenant
FROM pub.agg_finmodel_year
WHERE branch_id = 0
ORDER BY scenario, year
"""


@dataclass(frozen=True, slots=True)
class ModelBase:
    as_of: date
    capacity_mw: float
    opex_base: float
    opex_months: int
    opening_cash: float
    missing_fx: list[str]
    assumptions_at: datetime | None
    covenant: float


@dataclass(frozen=True, slots=True)
class LoadedModel:
    base: ModelBase
    years: dict[str, list[FinYear]]


def _opt(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _fin_year(r: RowMapping) -> FinYear:
    return FinYear(
        year=int(r["year"]), capacity_mw=float(r["capacity_mw"]),
        generation=float(r["generation"]), supply=float(r["supply"]),
        tariff=float(r["tariff"]), revenue=float(r["revenue"]), opex=float(r["opex"]),
        tax=float(r["tax"]), ebitda=float(r["ebitda"]), margin=_opt(r["margin"]),
        capex_plan=float(r["capex_plan"]), capex=float(r["capex"]),
        principal=float(r["principal"]), interest=float(r["interest"]),
        debt_service=float(r["debt_service"]), net_flow=float(r["net_flow"]),
        balance=float(r["balance"]), dscr=_opt(r["dscr"]),
        covenant_breach=bool(r["covenant_breach"]), unit_cost=_opt(r["unit_cost"]))


def load_model(db: Session) -> LoadedModel | None:
    rows = db.execute(text(_SQL)).mappings().all()
    if not rows:
        return None  # build yo'q yoki foydalanuvchi doirasi cheklangan (RLS: branch_id = 0)
    first = rows[0]
    base = ModelBase(
        as_of=from_date_id(int(first["as_of_id"])),
        capacity_mw=float(first["base_capacity_mw"]), opex_base=float(first["opex_base"]),
        opex_months=int(first["opex_months"]), opening_cash=float(first["opening_cash"]),
        missing_fx=[str(c) for c in first["missing_fx"]],
        assumptions_at=first["assumptions_at"], covenant=float(first["covenant"]))
    years: dict[str, list[FinYear]] = {}
    for r in rows:
        years.setdefault(str(r["scenario"]), []).append(_fin_year(r))
    return LoadedModel(base, years)


def assumptions_updated_at(db: Session) -> datetime | None:
    value: datetime | None = db.execute(text(
        "SELECT max(updated_at) FROM core.fin_assumptions WHERE is_current")).scalar_one()
    return value


def dscr_for_year(db: Session, year: int) -> float | None:
    """«Кредиты» DSCR (TZ 4): EBITDA года / обслуживание долга года — bazaviy ssenariy."""
    value = db.execute(text(
        "SELECT dscr FROM pub.agg_finmodel_year WHERE branch_id = 0 AND scenario = 'base' "
        "AND year = :y"), {"y": year}).scalar_one_or_none()
    return None if value is None else float(value)
