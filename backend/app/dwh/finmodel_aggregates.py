"""S5 финмодель agregati — Python bosqichi (`Aggregate.compute`, spec 3.4).

Build tranzaksiyasida (ugk_etl, scope_all): витрина kirishlari + joriy допущения → sof model
(`app.finmodel.model`) → 4 ssenariy × 7 yil. Qiymatlar mart ustunlari aniqligigacha yaxlitlanadi;
kirish bazasi (quvvat, xarajat bazasi, qoldiq, kursi yo'q valyutalar, допущения vaqti, ковенант)
har qatorga yoziladi — UI «Исходные данные модели» va «допущения изменены» belgisi uchun.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.dwh.aggregates import Aggregate, register
from app.dwh.dates import date_id, month_id
from app.finmodel.inputs import gather_inputs, load_assumptions
from app.finmodel.model import YearRow, run_model

_INSERT = """
INSERT INTO mart.agg_finmodel_year (
  build_id, branch_id, month_id, scenario, year, capacity_mw, generation, supply, tariff,
  revenue, opex, tax, ebitda, margin, capex_plan, capex, principal, interest, debt_service,
  net_flow, balance, dscr, covenant_breach, unit_cost, as_of_id, base_capacity_mw, opex_base,
  opex_months, opening_cash, missing_fx, assumptions_at, covenant)
VALUES (
  :build_id, 0, :month_id, :scenario, :year, :capacity_mw, :generation, :supply, :tariff,
  :revenue, :opex, :tax, :ebitda, :margin, :capex_plan, :capex, :principal, :interest,
  :debt_service, :net_flow, :balance, :dscr, :covenant_breach, :unit_cost, :as_of_id,
  :base_capacity_mw, :opex_base, :opex_months, :opening_cash, :missing_fx, :assumptions_at,
  :covenant)
"""
_MONEY = ("revenue", "opex", "tax", "ebitda", "capex_plan", "capex", "principal", "interest",
          "debt_service", "net_flow", "balance")


def _q(value: Decimal, places: str) -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _opt(value: Decimal | None, places: str) -> Decimal | None:
    return None if value is None else _q(value, places)


def _row(row: YearRow) -> dict[str, Any]:
    out: dict[str, Any] = {col: _q(getattr(row, col), "0.01") for col in _MONEY}
    out.update(
        year=row.year, capacity_mw=_q(row.capacity_mw, "0.01"),
        generation=_q(row.generation, "0.001"), supply=_q(row.supply, "0.001"),
        tariff=_q(row.tariff, "0.01"), margin=_opt(row.margin, "0.000001"),
        dscr=_opt(row.dscr, "0.0001"), covenant_breach=row.covenant_breach,
        unit_cost=_opt(row.unit_cost, "0.01"))
    return out


def compute_finmodel(conn: Connection, bound: Mapping[str, Any]) -> int:
    as_of = bound["as_of"]
    inputs, meta = gather_inputs(conn, as_of)
    assumptions = load_assumptions(conn)
    base = {
        "build_id": bound["build_id"], "month_id": month_id(as_of), "as_of_id": date_id(as_of),
        "base_capacity_mw": _q(inputs.capacity_mw, "0.01"),
        "opex_base": _q(inputs.opex_base, "0.01"), "opex_months": meta.opex_months,
        "opening_cash": _q(inputs.opening_cash, "0.01"), "missing_fx": list(meta.missing_fx),
        "assumptions_at": assumptions.updated_at, "covenant": assumptions.covenant,
    }
    rows = [{**base, "scenario": scenario, **_row(r)}
            for scenario, sa in assumptions.scenarios.items()
            for r in run_model(inputs, sa, covenant=assumptions.covenant)]
    conn.execute(text(_INSERT), rows)
    return len(rows)


FINMODEL_YEAR = register(Aggregate("agg_finmodel_year", (), compute_finmodel))
