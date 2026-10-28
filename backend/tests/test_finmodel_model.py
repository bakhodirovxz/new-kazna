from decimal import Decimal

import pytest

from app.finmodel.model import (
    DebtYear,
    FinInputs,
    ScalarAssumptions,
    ScenarioAssumptions,
    YearAssumptions,
    run_model,
    year_hours,
)
from app.finmodel.summary import from_row, sensitivity, summarize

D = Decimal
COVENANT = D("1.2")
INPUTS = FinInputs(
    capacity_mw=D(100), opex_base=D(100000), opening_cash=D(500),
    aip_plan={2026: D(30000), 2027: D(20000)},
    debt={2026: DebtYear(D(20000), D(10000), D(8000), D(2000)),
          2027: DebtYear(D(20000), D(8000), D(8000), D(1500))})
SCALARS = ScalarAssumptions(tariff_start=D(500), own_needs_share=D("0.02"),
                            capex_fx_share=D("0.4"))


def _year(**over: Decimal) -> YearAssumptions:
    base = {"tariff_growth": D("0.08"), "generation_factor": D(1), "fx_rate_factor": D(1),
            "opex_index": D("0.10"), "tax_rate": D("0.1"), "kium": D("0.5"),
            "capacity_add_mw": D(0)}
    base.update(over)
    return YearAssumptions(**base)


def scenario(name: str) -> ScenarioAssumptions:
    years: dict[int, YearAssumptions] = {}
    for year in (2026, 2027, 2028):
        over: dict[str, Decimal] = {}
        if year == 2027:
            over["capacity_add_mw"] = D(20)
        if name == "water" and year == 2027:
            over["generation_factor"] = D("0.85")
        if name == "tariff":
            over["tariff_growth"] = D("0.04")
        if name == "fx":
            over["fx_rate_factor"] = D("1.2")
        years[year] = _year(**over)
    return ScenarioAssumptions(years, SCALARS)


def q(value: Decimal | None, places: str = "0.0001") -> Decimal | None:
    return None if value is None else value.quantize(D(places))


def test_year_hours_leap() -> None:
    assert year_hours(2026) == 8760 and year_hours(2028) == 8784


def test_base_scenario_by_hand() -> None:
    y26, y27, y28 = run_model(INPUTS, scenario("base"), covenant=COVENANT)
    assert (y26.capacity_mw, y26.generation, y26.supply, y26.tariff) == (
        100, D("438"), D("429.24"), 500)
    assert (y26.revenue, y26.tax, y26.opex, y26.ebitda) == (
        D("214620"), D("21462"), D(100000), D("93158"))
    assert (y26.capex_plan, y26.capex, y26.principal, y26.interest, y26.debt_service) == (
        30000, 30000, 28000, 12000, 40000)
    assert (y26.net_flow, y26.balance, y26.dscr) == (D("23158"), D("23658"), D("2.32895"))
    assert q(y26.margin) == D("0.4341") and q(y26.unit_cost, "0.01") == D("282.97")
    assert not y26.covenant_breach
    assert (y27.capacity_mw, y27.generation, y27.tariff, y27.opex) == (
        120, D("525.6"), D("540"), D("110000"))
    assert (y27.revenue, y27.ebitda, y27.debt_service, y27.net_flow, y27.balance) == (
        D("278147.52"), D("140332.768"), 37500, D("82832.768"), D("106490.768"))
    assert q(y27.dscr) == D("3.7422")
    assert (y28.generation, y28.tariff, y28.opex) == (D("527.04"), D("583.2"), D("121000"))
    assert (y28.revenue, y28.ebitda, y28.capex, y28.debt_service) == (
        D("301222.33344"), D("150100.100096"), 0, 0)
    assert y28.dscr is None and not y28.covenant_breach
    assert y28.balance == D("256590.868096")


def test_water_tariff_fx_scenarios_by_hand() -> None:
    water = run_model(INPUTS, scenario("water"), covenant=COVENANT)
    assert (water[1].generation, water[1].revenue, water[1].ebitda) == (
        D("446.76"), D("236425.392"), D("102782.8528"))
    assert q(water[1].dscr) == D("2.7409") and water[1].balance == D("68940.8528")
    assert water[2].generation == D("527.04")  # маловодье faqat berilgan yillarda
    tariff = run_model(INPUTS, scenario("tariff"), covenant=COVENANT)
    assert (tariff[1].tariff, tariff[1].revenue, tariff[2].tariff) == (
        D("520"), D("267845.76"), D("540.8"))
    fx = run_model(INPUTS, scenario("fx"), covenant=COVENANT)
    assert (fx[0].capex, fx[0].principal, fx[0].interest, fx[0].debt_service) == (
        D("32400"), D("29600"), D("12400"), D("42000"))
    assert (fx[0].net_flow, fx[0].balance) == (D("18758"), D("19258"))
    assert q(fx[0].dscr) == D("2.2180")
    assert fx[0].ebitda == D("93158")  # kurs EBITDA'ga ta'sir qilmaydi (TZ formulasi)


def test_covenant_flag_uses_given_threshold() -> None:
    rows = run_model(INPUTS, scenario("base"), covenant=D("2.5"))
    assert [r.covenant_breach for r in rows] == [True, False, False]


def test_zero_capacity_has_no_division_by_zero() -> None:
    empty = FinInputs(capacity_mw=D(0), opex_base=D(1000), opening_cash=D(0), aip_plan={},
                      debt={2026: DebtYear(uzs_principal=D(100))})
    years = {2026: _year()}
    (row,) = run_model(empty, ScenarioAssumptions(years, SCALARS), covenant=COVENANT)
    assert row.revenue == 0 and row.margin is None and row.unit_cost is None
    assert row.ebitda == D(-1000) and row.dscr == D(-10) and row.covenant_breach
    assert row.balance == D(-1100)


def test_summary_and_verdict() -> None:
    rows = [from_row(r) for r in run_model(INPUTS, scenario("base"), covenant=COVENANT)]
    s = summarize("base", rows, base_capacity=100.0, covenant=1.2)
    assert (s.capacity_last, s.capacity_added, s.revenue_first) == (120.0, 20.0, 214620.0)
    assert s.revenue_last == pytest.approx(301222.33344)
    assert s.ebitda_total == pytest.approx(383590.868096)
    assert s.margin_avg == pytest.approx(0.4789633202)
    assert (s.capex_total, s.debt_service_total) == (50000.0, 77500.0)
    assert (s.dscr_min, s.dscr_min_year) == (pytest.approx(2.32895), 2026)
    assert s.cum_flow == pytest.approx(256090.868096)
    assert (s.negative_years, s.verdict) == (0, "funded")
    strict = summarize("base", rows, base_capacity=100.0, covenant=2.5)
    assert strict.verdict == "needs_financing"


def test_negative_balance_needs_financing() -> None:
    heavy = FinInputs(capacity_mw=INPUTS.capacity_mw, opex_base=INPUTS.opex_base,
                      opening_cash=INPUTS.opening_cash, aip_plan={2026: D(500000)},
                      debt=INPUTS.debt)
    rows = [from_row(r) for r in run_model(heavy, scenario("base"), covenant=COVENANT)]
    s = summarize("base", rows, base_capacity=100.0, covenant=1.2)
    assert rows[0].balance == pytest.approx(-446342.0)
    assert s.negative_years >= 1 and s.cum_flow < 0 and s.verdict == "needs_financing"


def test_sensitivity_against_base() -> None:
    summaries = {
        name: summarize(name, [from_row(r) for r in run_model(
            INPUTS, scenario(name), covenant=COVENANT)], base_capacity=100.0, covenant=1.2)
        for name in ("base", "water", "tariff", "fx")}
    out = sensitivity(summaries)
    assert [x.scenario for x in out] == ["water", "tariff", "fx"]
    assert out[0].delta_cum == pytest.approx(-37549.9152)
    assert out[1].delta_cum == pytest.approx(-28981.193472)
    assert out[2].delta_cum == pytest.approx(-7900.0)
    assert out[2].dscr_min == pytest.approx(2.2180476)
    assert sensitivity({k: v for k, v in summaries.items() if k != "base"}) == []
