from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import get_engine
from app.dwh.reference import current_setting
from app.etl.db import etl_transaction
from app.etl.synthetic.families import outlook
from app.etl.synthetic.families.investment import annual_plan
from app.etl.synthetic.model import SynthModel
from app.etl.synthetic.reference import OBJECTS
from app.finmodel.inputs import (
    InputsMeta,
    gather_inputs,
    load_assumptions,
    opex_excluded_items,
    opex_window,
)
from app.finmodel.model import DebtYear, FinInputs
from tests.etl_helpers import (
    FULL_WINDOW,
    TEST_AS_OF,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)
from tests.helpers import put_setting
from tests.s5_helpers import NO_RATE, finmodel_rows, finmodel_scenario


def _gather() -> tuple[FinInputs, InputsMeta]:
    with etl_transaction() as conn:
        return gather_inputs(conn, TEST_AS_OF)


def _debt(inputs: FinInputs, year: int) -> tuple[Decimal, ...]:
    d = inputs.debt.get(year, DebtYear())
    return d.uzs_principal, d.uzs_interest, d.fx_principal, d.fx_interest


def _delta(after: FinInputs, before: FinInputs, year: int) -> list[Decimal]:
    return [a - b for a, b in zip(_debt(after, year), _debt(before, year), strict=True)]


@pytest.fixture
def excluded_items() -> Iterator[tuple[str, str]]:
    """Ssenariyning EX va TX statyalarini sozlamalar orqali xarajat bazasidan chiqaradi."""
    tag = new_tag()
    with get_engine("app").connect() as conn:
        kinds = current_setting(conn, "kazna.calendar_kinds")
        excluded = current_setting(conn, "finmodel.opex_exclude_items")
    put_setting("kazna.calendar_kinds", {**kinds, "taxes": [*kinds.get("taxes", []),
                                                           f"TX-{tag}"]})
    put_setting("finmodel.opex_exclude_items", [*excluded, f"EX-{tag}"])
    yield tag, f"EX-{tag}"
    put_setting("kazna.calendar_kinds", kinds)
    put_setting("finmodel.opex_exclude_items", excluded)


def test_opex_window_is_last_twelve_closed_months() -> None:
    assert opex_window(date(2026, 9, 24)) == (date(2025, 9, 1), date(2026, 8, 31))
    assert opex_window(date(2026, 1, 1)) == (date(2025, 1, 1), date(2025, 12, 31))


def test_inputs_delta_from_scenario(excluded_items: tuple[str, str]) -> None:
    """Delta usuli: boshqa ma'lumot bo'lsa ham faqat ssenariy hissasi tekshiriladi."""
    tag, _ = excluded_items
    before, _ = _gather()
    source = new_source()
    try:
        run_id = open_run(source)
        stage(run_id, source, finmodel_rows(tag))
        merge_all(run_id, source)
        after, meta = _gather()
    finally:
        purge_source(source)
    assert after.capacity_mw - before.capacity_mw == Decimal("120.5")
    assert after.opex_base - before.opex_base == Decimal(1300)
    assert after.opening_cash - before.opening_cash == Decimal(800)
    for year, delta in ((2026, 300), (2027, 500), (2028, 0), (2032, 0)):
        got = after.aip_plan.get(year, Decimal(0)) - before.aip_plan.get(year, Decimal(0))
        assert got == Decimal(delta), year
    assert 2033 not in after.aip_plan
    assert _delta(after, before, 2026) == [Decimal(100), Decimal(30), Decimal(1100),
                                           Decimal(550)]
    assert _delta(after, before, 2027) == [Decimal(300), Decimal(18), Decimal(2200),
                                           Decimal(440)]
    assert meta.as_of == TEST_AS_OF and 1 <= meta.opex_months <= 12


def test_missing_fx_currency_excluded_and_listed() -> None:
    source = new_source()
    try:
        finmodel_scenario(source)
        _, meta = _gather()
    finally:
        purge_source(source)
    assert NO_RATE in meta.missing_fx
    _, cleaned = _gather()
    assert NO_RATE not in cleaned.missing_fx


def test_opex_excluded_items_merge_settings(excluded_items: tuple[str, str]) -> None:
    tag, ex = excluded_items
    with etl_transaction() as conn:
        codes = opex_excluded_items(conn)
    assert f"TX-{tag}" in codes and ex in codes and codes == sorted(set(codes))


def test_load_assumptions_four_scenarios() -> None:
    with get_engine("app").connect() as conn:
        a = load_assumptions(conn)
    assert set(a.scenarios) == {"base", "water", "tariff", "fx"}
    assert a.scenarios["water"].years[2028].generation_factor == Decimal("0.85")
    assert a.scenarios["tariff"].years[2030].tariff_growth == Decimal("0.04")
    assert a.scenarios["base"].years[2027].capacity_add_mw == Decimal(120)
    assert a.scenarios["fx"].scalars.tariff_start == Decimal(705)
    assert a.covenant == Decimal("1.2") and a.updated_at is not None


def test_load_assumptions_missing_row_fails() -> None:
    with get_engine("app").connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(text("UPDATE core.fin_assumptions SET is_current = false "
                              "WHERE scenario = 'fx' AND year = 2030 AND key = 'kium'"))
            with pytest.raises(ValueError, match="fx/2030/kium"):
                load_assumptions(conn)
        finally:
            tx.rollback()


class _Sink:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, Any]]] = []

    def add(self, target: str, row: Any) -> None:
        self.rows.append((target, dict(row)))


def test_outlook_family_rows() -> None:
    sink = _Sink()
    counts = outlook.generate(SynthModel(916202617, TEST_AS_OF), FULL_WINDOW, sink)
    rows = [r for t, r in sink.rows if t == "fact_investment"]
    assert counts == {"fact_investment": len(OBJECTS) * 3} == {"fact_investment": len(rows)}
    assert {r["date_id"] for r in rows} == {20270101, 20280101, 20290101}
    first = [r for r in rows if r["object_code"] == "OBJ-01"]
    assert [float(r["plan"]) for r in first] == pytest.approx(
        [annual_plan(1, 2026) * s for s in outlook.SHARES], rel=1e-4)
    assert all(r["doc_type"] == outlook.OUTLOOK_DOC and r["fact"] == 0
               and r["physical_pct"] is None for r in rows)
    late = _Sink()
    outlook.generate(SynthModel(916202617, date(2031, 3, 1)), FULL_WINDOW, late)
    assert {r["date_id"] // 10000 for _, r in late.rows} <= {2032}
