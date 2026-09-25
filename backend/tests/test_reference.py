from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.core.db import get_engine, new_session
from app.dwh.reference import (
    ALERT_RULES,
    DEFAULT_SETTINGS,
    current_setting,
    ensure_reference,
    validate_setting,
)
from app.etl.db import etl_transaction


def _rules() -> dict[str, dict[str, object]]:
    with get_engine("app").connect() as conn:
        rows = conn.execute(
            text("SELECT code, level, threshold, section, enabled FROM core.alert_rules "
                 "WHERE is_current")
        ).mappings().all()
    return {r["code"]: dict(r) for r in rows}


def test_twenty_alert_rules_with_tz_thresholds() -> None:
    rules = _rules()
    assert len(rules) == 20 == len(ALERT_RULES)
    assert sum(1 for r in rules.values() if r["level"] == "critical") == 5
    assert rules["cash_below_monthly_outflow"]["threshold"] == {
        "metric": "balance_to_avg_monthly_outflow", "op": "<", "value": 1.0}
    assert rules["payment_plan_execution"]["threshold"]["value"] == 0.9
    assert rules["contracts_overdue_90d"]["threshold"]["value"] == 90
    assert rules["contracts_overdue_90d"]["level"] == "critical"
    assert rules["procurement_overdue_lots"]["threshold"] == {
        "metric": "overdue_lots_count", "op": ">", "value": 3}
    assert rules["stock_below_minimum"]["level"] == "critical"
    assert rules["generation_plan"]["threshold"]["per"] == "station"
    assert rules["overtime"]["threshold"]["value"] == 20
    assert all(r["enabled"] for r in rules.values())


def test_fin_assumptions_four_scenarios() -> None:
    with get_engine("app").connect() as conn:
        rows = conn.execute(
            text("SELECT scenario, year, key, value FROM core.fin_assumptions WHERE is_current")
        ).all()
    values = {(s, y, k): v for s, y, k, v in rows}
    assert len(values) == 4 * 7 * 6
    assert {s for s, _, _ in values} == {"base", "water", "tariff", "fx"}
    assert values[("base", 2027, "tariff_growth")] == Decimal("0.08")
    assert values[("tariff", 2027, "tariff_growth")] == Decimal("0.04")
    assert values[("water", 2028, "generation_factor")] == Decimal("0.85")
    assert values[("water", 2026, "generation_factor")] == Decimal("1")
    assert values[("water", 2030, "generation_factor")] == Decimal("1")
    assert values[("fx", 2032, "fx_rate_factor")] == Decimal("1.2")


def test_settings_defaults_and_validation() -> None:
    with get_engine("app").connect() as conn:
        assert current_setting(conn, "freshness.max_age_hours") == 6
        assert current_setting(conn, "builds.keep") == 3
        assert current_setting(conn, "etl.history_start") == "2024-01-01"
    assert validate_setting("etl.synthetic_cron", "30 1 * * *") == "30 1 * * *"
    with pytest.raises(ValueError):
        validate_setting("etl.synthetic_cron", "every night")
    with pytest.raises(ValueError):
        validate_setting("freshness.max_age_hours", 0)
    with pytest.raises(ValueError):
        validate_setting("freshness.max_age_hours", True)
    with pytest.raises(KeyError):
        validate_setting("no.such", 1)
    assert set(DEFAULT_SETTINGS) == {
        "freshness.max_age_hours", "etl.history_start", "etl.synthetic_cron", "builds.keep",
        "retention.fact_years", "retention.audit_months", "partitions.months_ahead",
    }


def test_ensure_reference_is_idempotent_and_restores() -> None:
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DELETE FROM core.alert_rules WHERE code = 'overtime'"))
    with get_engine("app").begin() as conn:
        ensure_reference(conn)
        ensure_reference(conn)
    rules = _rules()
    assert len(rules) == 20
    with get_engine("app").connect() as conn:
        dv = conn.execute(text("SELECT count(*) FROM core.data_version WHERE id = 1")).scalar_one()
    assert dv == 1


def test_app_role_cannot_write_etl_journal() -> None:
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("INSERT INTO core.etl_run (source, mode, status) "
                       "VALUES ('x', 'full', 'running')"))


def test_etl_role_can_update_data_version_but_not_settings() -> None:
    with etl_transaction() as conn:
        conn.execute(text("UPDATE core.data_version SET published_at = published_at WHERE id = 1"))
    with pytest.raises(ProgrammingError, match="permission denied"), etl_transaction() as conn:
        conn.execute(text("UPDATE core.settings SET is_current = is_current"))


def test_staging_rows_table_is_unlogged() -> None:
    with etl_transaction() as conn:
        persistence = conn.execute(
            text("SELECT relpersistence FROM pg_class WHERE oid = 'stg.rows'::regclass")
        ).scalar_one()
    assert persistence == "u"
