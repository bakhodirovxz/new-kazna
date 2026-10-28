"""Финмодель kirishlari витринадан (worker, ugk_etl, scope_all) va допущения jadvalidan.

Faqat build `as_of` sanasigacha ma'lum bo'lgan faktlar (S5 spec 3.3):
- quvvat — `dim_branch_version` (`as_of` da amalda), stansiyalar (`ges`, `cascade`);
- xarajat bazasi — oxirgi 12 YOPILGAN oy operatsion rasxodi (`dwh.cashflow_effective`, S2
  ustuvorligi bilan), soliq/kredit statyalari (`kazna.calendar_kinds`) va
  `finmodel.opex_exclude_items` siz; yillikka keltirilmaydi (qator soni `opex_months`);
- boshlang'ich qoldiq — har hisobning `as_of` gacha oxirgi `fact_balance` qiymati yig'indisi;
- АИП rejasi — `fact_investment.plan` yillar bo'yicha (forward qatorlar);
- kredit grafigi — yillar bo'yicha; valyuta — `as_of` gacha oxirgi ЦБ kursi, kursi yo'q valyuta
  hisobga olinmaydi va `missing_fx` ga yoziladi (S2 qarori).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.dwh.dates import add_months, date_id, month_start
from app.dwh.reference import (
    FIN_FIRST_YEAR,
    FIN_SCALAR_KEYS,
    FIN_YEAR_KEYS,
    FIN_YEARS,
    SCENARIOS,
    current_setting,
)
from app.finmodel.model import (
    ZERO,
    DebtYear,
    FinInputs,
    ScalarAssumptions,
    ScenarioAssumptions,
    YearAssumptions,
)

_CAPACITY = """
SELECT coalesce(sum(v.capacity_mw), 0)
FROM dwh.dim_branch b
JOIN dwh.dim_branch_version v ON v.branch_id = b.branch_id
 AND CAST(:as_of AS date) BETWEEN v.valid_from AND coalesce(v.valid_to, DATE '9999-12-31')
WHERE b.kind IN ('ges', 'cascade')
"""

_OPEX = """
SELECT coalesce(sum(f.amount), 0) AS amount, count(DISTINCT d.month_id) AS months
FROM dwh.cashflow_effective f
JOIN dwh.dim_date d ON d.date_id = f.date_id
JOIN dwh.dim_item i ON i.item_id = f.item_id
WHERE f.direction = 'out' AND i.activity = 'operating'
  AND NOT (i.code = ANY(CAST(:excluded AS text[])))
  AND f.date_id BETWEEN :from_id AND :to_id
"""

_CASH = """
SELECT coalesce(sum(z.balance), 0) FROM (
  SELECT DISTINCT ON (fb.branch_id, fb.bank_id) fb.balance
  FROM dwh.balance_effective fb
  WHERE fb.date_id <= :as_of_id
  ORDER BY fb.branch_id, fb.bank_id, fb.date_id DESC) z
"""

_AIP = """
SELECT d.year, sum(i.plan) AS plan
FROM dwh.investment_effective i
JOIN dwh.dim_date d ON d.date_id = i.date_id
WHERE d.year BETWEEN :y0 AND :y1
GROUP BY d.year
"""

_DEBT = """
WITH rates AS (
  SELECT DISTINCT ON (currency) currency, rate
  FROM dwh.fx_rate WHERE date_id <= :as_of_id
  ORDER BY currency, date_id DESC)
SELECT d.year, l.currency, sum(s.principal) AS principal, sum(s.interest) AS interest,
       max(r.rate) AS rate
FROM dwh.loan_schedule_effective s
JOIN dwh.dim_loan l ON l.loan_id = s.loan_id
JOIN dwh.dim_date d ON d.date_id = s.date_id
LEFT JOIN rates r ON r.currency = l.currency
WHERE d.year BETWEEN :y0 AND :y1
GROUP BY d.year, l.currency
"""


@dataclass(frozen=True, slots=True)
class InputsMeta:
    as_of: date
    opex_months: int  # xarajat bazasida ma'lumoti bor oylar (12 dan kam — UI ogohlantiradi)
    missing_fx: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Assumptions:
    scenarios: dict[str, ScenarioAssumptions]
    updated_at: datetime | None  # joriy допущения'ning eng so'nggi o'zgarishi
    covenant: Decimal


def opex_window(as_of: date) -> tuple[date, date]:
    first = month_start(as_of)
    return add_months(first, -12), first - timedelta(days=1)


def opex_excluded_items(conn: Connection) -> list[str]:
    kinds = current_setting(conn, "kazna.calendar_kinds")
    extra = current_setting(conn, "finmodel.opex_exclude_items")
    return sorted({*kinds.get("taxes", []), *kinds.get("loans", []), *extra})


def gather_inputs(conn: Connection, as_of: date) -> tuple[FinInputs, InputsMeta]:
    years = {"y0": FIN_YEARS[0], "y1": FIN_YEARS[-1]}
    as_of_id = date_id(as_of)
    capacity = Decimal(conn.execute(text(_CAPACITY), {"as_of": as_of}).scalar_one())
    start, end = opex_window(as_of)
    opex = conn.execute(text(_OPEX), {"excluded": opex_excluded_items(conn),
                                      "from_id": date_id(start), "to_id": date_id(end)}).one()
    cash = Decimal(conn.execute(text(_CASH), {"as_of_id": as_of_id}).scalar_one())
    aip = {int(r.year): Decimal(r.plan) for r in conn.execute(text(_AIP), years)}
    parts: dict[int, list[Decimal]] = {}
    missing: set[str] = set()
    for r in conn.execute(text(_DEBT), {**years, "as_of_id": as_of_id}):
        acc = parts.setdefault(int(r.year), [ZERO, ZERO, ZERO, ZERO])
        if r.currency == "UZS":
            acc[0] += r.principal
            acc[1] += r.interest
        elif r.rate is None:
            missing.add(str(r.currency))
        else:
            acc[2] += r.principal * r.rate
            acc[3] += r.interest * r.rate
    debt = {year: DebtYear(*acc) for year, acc in parts.items()}
    inputs = FinInputs(capacity_mw=capacity, opex_base=Decimal(opex.amount), opening_cash=cash,
                       aip_plan=aip, debt=debt)
    return inputs, InputsMeta(as_of, int(opex.months), tuple(sorted(missing)))


def _need(values: dict[tuple[str, int, str], Decimal], scenario: str, year: int,
          key: str) -> Decimal:
    try:
        return values[(scenario, year, key)]
    except KeyError:
        raise ValueError(f"финмодель: допущение {scenario}/{year}/{key} yo'q") from None


def load_assumptions(conn: Connection) -> Assumptions:
    rows = conn.execute(text(
        "SELECT scenario, year, key, value, updated_at FROM core.fin_assumptions "
        "WHERE is_current")).all()
    values = {(str(r.scenario), int(r.year), str(r.key)): Decimal(r.value) for r in rows}
    scenarios: dict[str, ScenarioAssumptions] = {}
    for scenario in SCENARIOS:
        years = {year: YearAssumptions(**{k: _need(values, scenario, year, k)
                                          for k in FIN_YEAR_KEYS}) for year in FIN_YEARS}
        scalars = ScalarAssumptions(**{k: _need(values, scenario, FIN_FIRST_YEAR, k)
                                       for k in FIN_SCALAR_KEYS})
        scenarios[scenario] = ScenarioAssumptions(years, scalars)
    covenant = Decimal(str(current_setting(conn, "finmodel.dscr_covenant")))
    updated = max((r.updated_at for r in rows), default=None)
    return Assumptions(scenarios, updated, covenant)
