import json
import logging
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from app import worker
from app.core import integrations
from app.core.config import get_settings
from app.core.db import get_engine
from app.etl.db import etl_transaction
from app.etl.hr import attendance
from app.etl.hr.client import HrApiClient
from app.etl.hr.models import parse_attendance
from app.etl.types import ConnectorUnavailableError
from tests.etl_helpers import RecordingNotifier
from tests.helpers import clear_setting, put_setting

FIXTURE = (Path(__file__).parent / "fixtures" / "hr" / "attendance.json").read_bytes()
DAY = date(2026, 10, 28)
ORGS = [{"org": "x", "branch_code": "UGE-01", "hr_id": 1},
        {"org": "y", "branch_code": "UGE-02", "hr_id": 6}]  # id 25 (sho'ba) — moslashtirilmagan


def report():  # type: ignore[no-untyped-def]
    return parse_attendance(json.loads(FIXTURE))


def _clear() -> None:
    with etl_transaction() as conn:
        conn.execute(text("DELETE FROM dwh.fact_attendance WHERE att_date >= '2026-10-01'"))


@pytest.fixture
def orgs() -> Iterator[None]:
    _clear()
    put_setting("hr.orgs", ORGS)
    yield
    put_setting("hr.orgs", [])
    clear_setting("hr.base_url")
    with get_engine("app").begin() as conn:
        integrations.clear_secret(conn, "hr.api_key")
    _clear()


def test_table_has_forced_rls_and_grants() -> None:
    with etl_transaction() as conn:
        row = conn.execute(text(
            "SELECT c.relrowsecurity, c.relforcerowsecurity, "
            "has_table_privilege('ugk_app', 'dwh.fact_attendance', 'SELECT') AS app_sel, "
            "has_table_privilege('ugk_app', 'dwh.fact_attendance', 'INSERT') AS app_ins, "
            "has_table_privilege('ugk_etl', 'dwh.fact_attendance', 'INSERT') AS etl_ins "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'dwh' AND c.relname = 'fact_attendance'")).one()
        pol = conn.execute(text("SELECT count(*) FROM pg_policies WHERE schemaname = 'dwh' "
                                "AND tablename = 'fact_attendance'")).scalar_one()
    assert (row.relrowsecurity, row.relforcerowsecurity, row.app_sel, row.app_ins,
            row.etl_ins) == (True, True, True, False, True) and pol == 1


def test_store_maps_by_id_is_idempotent_and_keeps_no_names(orgs: None) -> None:
    with etl_transaction() as conn:
        first = attendance.store(conn, report(), [attendance.HrOrg.model_validate(o)
                                                  for o in ORGS])
        again = attendance.store(conn, report(), [attendance.HrOrg.model_validate(o)
                                                  for o in ORGS])
        rows = conn.execute(text(
            "SELECT b.code, a.status_code, a.status_label, a.status_kind, a.employees, "
            "a.person_days, a.branch_employees, a.generated_at FROM dwh.fact_attendance a "
            "JOIN dwh.dim_branch b USING (branch_id) WHERE a.att_date = :d "
            "ORDER BY b.code, a.status_code"), {"d": DAY}).all()
    assert (first.stored, first.skipped_branches) == (9, 1) and again.stored == 9
    assert len(rows) == 9
    got = {(r.code, r.status_code): r for r in rows}
    late = got[("UGE-01", "late")]
    assert (late.status_label, late.status_kind, late.employees, late.person_days,
            late.branch_employees) == ("Kech qolgan", "attendance", 4, 4, 30)
    assert late.generated_at == datetime(2026, 10, 28, 6, 12, 41, 508000, tzinfo=UTC)
    assert got[("UGE-02", "new_reason")].status_label == "Yangi sabab"
    assert ("UGE-01", "dismissed") not in got
    dump = json.dumps([tuple(map(str, r)) for r in rows], ensure_ascii=False)
    assert "Каримов" not in dump and "12345678901234" not in dump


def _client(status: int = 200) -> HrApiClient:
    return HrApiClient("https://hr.test", "k3y-SECRET-123", transport=httpx.MockTransport(
        lambda _r: httpx.Response(status, content=FIXTURE)))


def test_poll_fetches_one_day_and_stores(orgs: None, caplog: pytest.LogCaptureFixture,
                                         capsys: pytest.CaptureFixture[str]) -> None:
    caplog.set_level(logging.DEBUG)
    result = attendance.poll_attendance(get_settings(), DAY, client=_client())
    assert result.stored == 9
    with etl_transaction() as conn:
        n = conn.execute(text("SELECT count(*) FROM dwh.fact_attendance WHERE att_date = :d"),
                         {"d": DAY}).scalar_one()
    assert n == 9
    out = capsys.readouterr()
    for secret in ("Каримов", "k3y-SECRET-123", "12345678901234"):
        assert secret not in caplog.text and secret not in out.out + out.err


def test_jobs_skip_silently_without_key_and_swallow_errors(
        orgs: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    jobs = {j.id for j in worker.build_scheduler(get_settings(), RecordingNotifier()).get_jobs()}
    assert {"hr_attendance", "hr_attendance_nightly"} <= jobs

    def boom(*_a: object, **_k: object) -> None:
        raise AssertionError("tarmoq so'ralmasligi kerak")

    monkeypatch.setattr(attendance, "HrApiClient", boom)
    attendance.attendance_job(get_settings())  # kalit yo'q — o'tkazib yuboradi
    with get_engine("app").begin() as conn:
        integrations.store_secret(conn, "hr.api_key", "k3y-SECRET-123", None)
    put_setting("hr.base_url", "")
    attendance.attendance_job(get_settings())  # manzil yo'q — o'tkazib yuboradi
    put_setting("hr.base_url", "https://hr.test")

    def unavailable(*_a: object, **_k: object) -> None:
        raise ConnectorUnavailableError("HR API: HTTP 503")

    monkeypatch.setattr(attendance, "poll_attendance", unavailable)
    attendance.attendance_job(get_settings())  # xato log'ga yoziladi, ko'tarilmaydi
    attendance.attendance_job(get_settings(), days_back=1)
    assert "k3y-SECRET-123" not in caplog.text
