from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import apply_rls, new_session
from app.dwh import builds
from app.etl.db import etl_transaction
from app.etl.file_connector import FileConnector
from app.etl.runner import Runner
from app.etl.types import Mode
from tests.etl_helpers import (
    TEST_AS_OF,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)
from tests.s1_helpers import rebuild
from tests.s2_helpers import LoanScenario, loan_rows, loan_scenario

TABLES = ("agg_loan_month", "agg_loan_schedule")


@pytest.fixture
def sc() -> Iterator[LoanScenario]:
    source = new_source()
    yield loan_scenario(source)
    purge_source(source)


def _rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    with etl_transaction() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def _opt(value: Any) -> float | None:
    return None if value is None else float(value)


def test_loan_month_snapshots(sc: LoanScenario) -> None:
    rows = _rows("SELECT month_id, loan_id, snap_date_id, rate, fx_rate, original_cur, "
                 "outstanding_cur, outstanding FROM mart.agg_loan_month WHERE build_id = :b "
                 "AND branch_id = :br AND month_id IN (202601, 202608, 202609)",
                 b=sc.build_id, br=sc.branch_id)
    got = {(r["month_id"], r["loan_id"]): (r["snap_date_id"], float(r["rate"]), _opt(r["fx_rate"]),
                                           float(r["original_cur"]), float(r["outstanding_cur"]),
                                           _opt(r["outstanding"])) for r in rows}
    a, b = sc.loan_a, sc.loan_b
    assert got == {
        (202601, a): (20260131, 0.05, None, 10.0, 10.0, None),
        (202601, b): (20260131, 0.18, 1.0, 500.0, 500.0, 500.0),
        (202608, a): (20260831, 0.05, 1000.0, 10.0, 9.0, 9000.0),
        (202608, b): (20260831, 0.18, 1.0, 500.0, 400.0, 400.0),
        (202609, a): (20260924, 0.05, 1100.0, 10.0, 8.0, 8800.0),
        (202609, b): (20260924, 0.18, 1.0, 500.0, 400.0, 400.0),
    }
    meta = _rows("SELECT loan_code, creditor, currency, grace_until, maturity "
                 "FROM mart.agg_loan_month WHERE build_id = :b AND loan_id = :loan "
                 "AND month_id = 202608", b=sc.build_id, loan=a)[0]
    assert meta["loan_code"] == f"LA-{sc.tag}" and meta["currency"] == "XTL"
    assert meta["creditor"] == f"Тест кредитор А {sc.tag}"
    assert (meta["grace_until"], meta["maturity"]) == (date(2026, 1, 1), date(2028, 12, 31))


def test_loan_without_schedule_is_skipped(sc: LoanScenario) -> None:
    assert _rows("SELECT 1 FROM mart.agg_loan_month WHERE build_id = :b AND loan_code = :c",
                 b=sc.build_id, c=f"LC-{sc.tag}") == []


def test_schedule_rows_copied(sc: LoanScenario) -> None:
    rows = _rows("SELECT month_id, date_id, principal_cur, interest_cur, balance_cur "
                 "FROM mart.agg_loan_schedule WHERE build_id = :b AND branch_id = :br "
                 "ORDER BY date_id", b=sc.build_id, br=sc.branch_id)
    assert [(r["date_id"], float(r["principal_cur"]), float(r["interest_cur"]),
             float(r["balance_cur"])) for r in rows] == [
        (20260315, 1.0, 0.5, 9.0), (20260610, 100.0, 30.0, 400.0), (20260915, 1.0, 0.46, 8.0),
        (20261010, 100.0, 18.0, 300.0), (20270315, 1.0, 0.4, 7.0), (20271010, 300.0, 18.0, 0.0),
        (20280315, 7.0, 0.35, 0.0)]
    assert rows[-1]["month_id"] == 202803


def test_rate_version_applies_from_change_date(sc: LoanScenario) -> None:
    run = open_run(sc.source)
    changed = {**loan_rows(sc.tag)["dim_loan"][0], "rate": 0.06}
    stage(run, sc.source, {"dim_loan": [changed]})
    merge_all(run, sc.source, as_of=date(2026, 9, 1))
    build_id = rebuild(run)
    rows = _rows("SELECT month_id, rate FROM mart.agg_loan_month WHERE build_id = :b "
                 "AND loan_id = :loan AND month_id IN (202608, 202609)", b=build_id, loan=sc.loan_a)
    assert {r["month_id"]: float(r["rate"]) for r in rows} == {202608: 0.05, 202609: 0.06}


def test_rls_and_failed_build(sc: LoanScenario) -> None:
    for table in TABLES:
        with new_session() as s:
            apply_rls(s, frozenset({sc.branch_id}))
            seen = set(s.execute(text(f"SELECT DISTINCT branch_id FROM mart.{table} "
                                      "WHERE build_id = :b"), {"b": sc.build_id}).scalars())
        assert seen == {sc.branch_id}, table
    with etl_transaction() as conn:
        builds.mark_failed(conn, sc.build_id)
        for table in TABLES:
            count = conn.execute(text(f"SELECT count(*) FROM mart.{table} WHERE build_id = :b"),
                                 {"b": sc.build_id}).scalar_one()
            assert count == 0, table


def test_file_connector_keeps_future_loan_rows(tmp_path: Path) -> None:
    source = new_source()
    tag = new_tag()
    try:
        (tmp_path / "dim_branch.csv").write_text(
            "code;name;short_name;kind;capacity_mw;sort_order\n"
            f"T-{tag};Тестовая ГЭС;Т;ges;10;99\n", encoding="utf-8")
        (tmp_path / "dim_loan.csv").write_text(
            "code;creditor;project;currency;rate;grace_until;maturity;amount_uzs;branch_code\n"
            f"LF-{tag};Банк;Проект;UZS;0.1;;2030-12-31;100;T-{tag}\n", encoding="utf-8")
        (tmp_path / "fact_loan_schedule.csv").write_text(
            "doc_type;src_id;date;branch_code;loan_code;principal;interest;balance\n"
            f"loan_schedule;f1;2026-03-15;T-{tag};LF-{tag};10;5;90\n"
            f"loan_schedule;f2;2029-03-15;T-{tag};LF-{tag};90;5;0\n", encoding="utf-8")
        # Ikkinchi to'liq yuklash ham kelajak qatorini o'chirmasligi kerak (forward almashtirish).
        for _ in range(2):
            result = Runner(FileConnector(tmp_path, source=source), mode=Mode.FULL,
                            today=TEST_AS_OF, sleep=lambda _: None).run()
            assert result.status == "success", result
        with etl_transaction() as conn:
            ids = set(conn.execute(text("SELECT src_id FROM dwh.fact_loan_schedule "
                                        "WHERE src_system = :s"), {"s": source}).scalars())
        assert ids == {"f1", "f2"}
    finally:
        purge_source(source)
