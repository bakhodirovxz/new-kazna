from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.admin.dwh_schemas import FinAssumptionItem
from app.core.db import get_engine
from app.dwh import aggregates, builds
from app.dwh.aggregates import Aggregate, BuildParams
from app.dwh.reference import (
    DEFAULT_SETTINGS,
    FIN_FIRST_YEAR,
    FIN_KEY_BOUNDS,
    FIN_KEYS,
    FIN_SCALAR_KEYS,
    FIN_YEAR_KEYS,
    fin_assumption_seeds,
    fin_value_error,
    validate_setting,
)
from app.etl.db import SCOPE_ALL_SQL

NEW_KEYS = ("capacity_add_mw", "tariff_start", "own_needs_share", "capex_fx_share")


def test_keys_and_bounds() -> None:
    assert FIN_YEAR_KEYS[-1] == "capacity_add_mw"
    assert FIN_SCALAR_KEYS == ("tariff_start", "own_needs_share", "capex_fx_share")
    assert FIN_KEYS == FIN_YEAR_KEYS + FIN_SCALAR_KEYS and FIN_FIRST_YEAR == 2026
    assert set(FIN_KEY_BOUNDS) == set(FIN_KEYS)
    assert all(low < high for low, high in FIN_KEY_BOUNDS.values())


def test_seeds_scalar_keys_only_in_first_year() -> None:
    rows = fin_assumption_seeds()
    assert len(rows) == 4 * 7 * 7 + 4 * 3
    assert {r[1] for r in rows if r[2] in FIN_SCALAR_KEYS} == {2026}
    values = {(s, y, k): v for s, y, k, v in rows}
    assert values[("base", 2026, "capacity_add_mw")] == 0
    assert values[("base", 2027, "capacity_add_mw")] == Decimal(120)
    assert values[("fx", 2032, "capacity_add_mw")] == Decimal(30)
    assert values[("water", 2026, "tariff_start")] == Decimal(705)
    assert values[("base", 2026, "own_needs_share")] == Decimal("0.016")
    assert values[("tariff", 2026, "capex_fx_share")] == Decimal("0.4")
    assert values[("water", 2028, "generation_factor")] == Decimal("0.85")
    assert all(fin_value_error(y, k, v) is None for (_s, y, k), v in values.items())


def test_new_seed_rows_in_database() -> None:
    with get_engine("app").connect() as conn:
        count = conn.execute(text(
            "SELECT count(*) FROM core.fin_assumptions WHERE is_current AND key = ANY(:k)"),
            {"k": list(NEW_KEYS)}).scalar_one()
    assert count == 4 * 7 + 4 * 3


@pytest.mark.parametrize(("year", "key", "value", "error"), [
    (2027, "tariff_start", Decimal(700), "year"),
    (2026, "tariff_start", Decimal(0), "value"),
    (2026, "kium", Decimal("1.5"), "value"),
    (2026, "kium", Decimal("0.04"), "value"),
    (2030, "generation_factor", Decimal("0.05"), "value"),
    (2026, "tariff_start", Decimal(9), "value"),
    (2030, "capacity_add_mw", Decimal(-1), "value"),
    (2026, "magic", Decimal(1), "key"),
    (2026, "tariff_start", Decimal(705), None),
    (2031, "capacity_add_mw", Decimal(300), None),
    (2027, "fx_rate_factor", Decimal("1.2"), None),
])
def test_fin_value_error(year: int, key: str, value: Decimal, error: str | None) -> None:
    assert fin_value_error(year, key, value) == error


def test_admin_item_uses_key_bounds() -> None:
    item = FinAssumptionItem(scenario="base", year=2026, key="tariff_start", value=750)
    assert item.value == 750
    bad: list[dict[str, Any]] = [
        {"year": 2027, "key": "tariff_start", "value": 750},
        {"year": 2026, "key": "kium", "value": 2},
        {"year": 2026, "key": "magic", "value": 1},
        {"year": 2040, "key": "kium", "value": 0.4},
        {"year": 2027, "key": "capacity_add_mw", "value": float("nan")},
    ]
    for fields in bad:
        with pytest.raises(ValueError):
            FinAssumptionItem(scenario="base", **fields)


def test_finmodel_settings() -> None:
    assert DEFAULT_SETTINGS["finmodel.dscr_covenant"] == 1.2
    assert DEFAULT_SETTINGS["finmodel.opex_exclude_items"] == []
    assert validate_setting("finmodel.dscr_covenant", 1.35) == 1.35
    assert validate_setting("finmodel.opex_exclude_items", ["1C-O-abc"]) == ["1C-O-abc"]
    bad: list[tuple[str, Any]] = [
        ("finmodel.dscr_covenant", 0.4), ("finmodel.dscr_covenant", "1.2"),
        ("finmodel.dscr_covenant", 6), ("finmodel.opex_exclude_items", [""]),
        ("finmodel.opex_exclude_items", ["A", "A"]),
        ("finmodel.opex_exclude_items", [f"X{i}" for i in range(201)]),
    ]
    for key, value in bad:
        with pytest.raises(ValueError):
            validate_setting(key, value)


def test_aggregate_compute_default_is_none() -> None:
    assert Aggregate("agg_x", ("SELECT 1",)).compute is None


def test_build_all_calls_compute(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[int, date]] = []

    def compute(conn: Connection, bound: Mapping[str, Any]) -> int:
        seen.append((int(bound["build_id"]), bound["as_of"]))
        return 3

    monkeypatch.setattr(aggregates, "AGGREGATES", [Aggregate("agg_cash_month", (), compute)])
    with get_engine("etl").connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(text(SCOPE_ALL_SQL))
            build_id = builds.create_build(conn, None)
            out = aggregates.build_all(conn, build_id, BuildParams(
                as_of=date(2026, 9, 24), date_from=date(2025, 1, 1)))
        finally:
            tx.rollback()
    assert seen == [(build_id, date(2026, 9, 24))]
    assert out["agg_cash_month"] >= 3
