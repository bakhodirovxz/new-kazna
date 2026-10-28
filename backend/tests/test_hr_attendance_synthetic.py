from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.dwh.dates import today_tashkent
from app.etl.db import etl_transaction
from app.etl.hr import attendance
from app.etl.synthetic import SyntheticConnector
from app.etl.synthetic.families.attendance import seed_attendance

NOW = datetime(2026, 10, 28, 6, 0, tzinfo=UTC)
WEEKDAY, SUNDAY = date(2026, 10, 28), date(2026, 10, 25)


def _connector() -> SyntheticConnector:
    return SyntheticConnector(as_of=WEEKDAY)


def test_report_is_deterministic_covers_16_branches_and_adds_up() -> None:
    a, b = _connector().attendance(WEEKDAY, NOW), _connector().attendance(WEEKDAY, NOW)
    assert a == b and len(a.branches) == 16
    for branch in a.branches:
        assert sum(n for _d, n in branch.by_status.values()) == branch.employees
        assert branch.by_status["present"][1] > branch.employees * 0.6
    assert {s.code for s in a.statuses} >= {"present", "late", "absent", "business_trip"}
    sunday = _connector().attendance(SUNDAY, NOW)
    assert all(br.by_status["day_off"][1] == br.employees for br in sunday.branches)
    assert a != _connector().attendance(date(2026, 10, 27), NOW)


@pytest.fixture
def clean() -> Iterator[None]:
    with etl_transaction() as conn:
        conn.execute(text("DELETE FROM dwh.fact_attendance"))
    yield
    with etl_transaction() as conn:
        conn.execute(text("DELETE FROM dwh.fact_attendance"))


def test_seed_writes_days_idempotently(clean: None) -> None:
    with etl_transaction() as conn:
        first = seed_attendance(conn, _connector().model, WEEKDAY, days=3, now=NOW)
        second = seed_attendance(conn, _connector().model, WEEKDAY, days=3, now=NOW)
        rows = conn.execute(text("SELECT count(*), count(DISTINCT branch_id), "
                                 "count(DISTINCT att_date) FROM dwh.fact_attendance")).one()
    assert first.stored == second.stored == 3 * 16 * 8 == rows[0]
    assert rows[1:] == (16, 3)


def test_dev_worker_refreshes_demo_when_hr_not_configured(clean: None) -> None:
    dev = get_settings().model_copy(update={"env": "dev"})
    attendance.attendance_job(dev)
    with etl_transaction() as conn:
        n = conn.execute(text("SELECT count(DISTINCT branch_id) FROM dwh.fact_attendance "
                              "WHERE att_date = :d"), {"d": today_tashkent()}).scalar_one()
    assert n == 16
    with etl_transaction() as conn:
        conn.execute(text("DELETE FROM dwh.fact_attendance"))
    attendance.attendance_job(get_settings().model_copy(update={"env": "prod"}))
    with etl_transaction() as conn:
        assert conn.execute(text("SELECT count(*) FROM dwh.fact_attendance")).scalar_one() == 0

