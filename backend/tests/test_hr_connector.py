import json
import logging
from collections.abc import Iterator, Mapping
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app import cli, worker
from app.core import integrations
from app.core.config import ConfigError, get_settings
from app.core.db import get_engine
from app.dwh.reference import current_setting
from app.etl.connectors import KNOWN_SOURCES, make_connector
from app.etl.db import etl_transaction
from app.etl.hr.connector import HrConnector, position_code
from app.etl.hr.models import parse_breakdown
from app.etl.hr.registry import HrOrg
from app.etl.hr.source import HrSnapshot
from app.etl.runner import Runner
from app.etl.staging import DbStagingSink
from app.etl.types import HealthResult, Mode, Window
from tests.etl_helpers import (
    TEST_AS_OF,
    RecordingNotifier,
    branch_row,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)
from tests.helpers import clear_setting, put_setting

FIXTURES = Path(__file__).parent / "fixtures" / "hr"
WINDOW = Window(date(2026, 9, 1), TEST_AS_OF)
ORGS = [HrOrg(org="Чорвоқ ГЭС", branch_code="UGE-02"), HrOrg(org="Фарҳод ГЭС",
                                                                branch_code="UGE-05")]


class ReportSink:
    def __init__(self) -> None:
        self.load_id = 0
        self.rows: list[tuple[str, dict[str, Any]]] = []
        self.errors: list[tuple[str, str, str, str]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))

    def error(self, *, target: str, code: str, message: str, src_id: str | None = None,
              severity: str = "error") -> None:
        self.errors.append((target, code, message, severity))


class FakeSource:
    name = "fake"

    def __init__(self, fixture: str, total: int | None = 100) -> None:
        data = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
        self.rows = tuple(parse_breakdown(data))
        self.total = total

    def healthcheck(self) -> HealthResult:
        return HealthResult(True, "fake")

    def snapshot(self, today: date) -> HrSnapshot:
        return HrSnapshot(today, self.rows, self.total)


def _extract(source: FakeSource, orgs: list[HrOrg] = ORGS) -> ReportSink:
    sink = ReportSink()
    HrConnector(source, orgs, today=lambda: TEST_AS_OF).extract(WINDOW, sink)
    return sink


def test_org_breakdown_is_mapped_to_fact_hr(caplog: pytest.LogCaptureFixture,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    caplog.set_level(logging.DEBUG)
    sink = _extract(FakeSource("by_org.json"))
    facts = {r["src_id"]: r for t, r in sink.rows if t == "fact_hr"}
    lead, oper = position_code("Руководители"), position_code("Оперативный персонал")
    assert set(facts) == {f"UGE-02:{lead}:202609", f"UGE-02:{oper}:202609",
                          f"UGE-05:{lead}:202609"}
    row = facts[f"UGE-02:{oper}:202609"]
    assert (row["date_id"], row["headcount_plan"], row["headcount_fact"], row["hired"],
            row["fired"], row["overtime_hours"], row["payroll"]) == (
        20260924, 90, 81, 2, 3, 400, 0)
    assert facts[f"UGE-05:{lead}:202609"]["headcount_plan"] == 0  # штат noma'lum
    positions = {r["code"]: r for t, r in sink.rows if t == "dim_position"}
    assert positions[lead] == {"code": lead, "category": "Руководители", "department": "—"}
    assert [(c, s) for _, c, _, s in sink.errors] == [("unmapped_org", "error"),
                                                      ("total_mismatch", "warning")]
    everything = json.dumps([sink.rows, sink.errors], ensure_ascii=False, default=str)
    captured = capsys.readouterr()
    for secret in ("Иванов", "12345678901234"):
        assert secret not in everything and secret not in caplog.text
        assert secret not in captured.out and secret not in captured.err


def test_no_org_breakdown_is_a_warning() -> None:
    sink = _extract(FakeSource("by_category.json"))
    assert [t for t, _ in sink.rows] == []
    assert [(c, s) for _, c, _, s in sink.errors] == [("no_branch_breakdown", "warning")]


def test_requires_reporting_sink() -> None:
    class Plain:
        def add(self, target: str, row: Mapping[str, Any]) -> None: ...

    with pytest.raises(TypeError):
        HrConnector(FakeSource("by_org.json"), ORGS).extract(WINDOW, Plain())


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def test_runner_loads_idempotently(source: str) -> None:
    tag = new_tag()
    a, b = branch_row(tag), branch_row(f"{tag}B")
    run = open_run(source)
    stage(run, source, {"dim_branch": [a, b]})
    merge_all(run, source)
    orgs = [HrOrg(org="Чорвоқ ГЭС", branch_code=a["code"]),
            HrOrg(org="Фарҳод ГЭС", branch_code=b["code"]),
            HrOrg(org="Неизвестный филиал", branch_code=b["code"])]
    for _ in range(2):
        connector = HrConnector(FakeSource("by_org.json", total=98), orgs, source_name=source,
                                today=lambda: TEST_AS_OF)
        result = Runner(connector, mode=Mode.INCREMENTAL, today=TEST_AS_OF,
                        sleep=lambda _: None).run()
        assert result.status == "success", result
    with etl_transaction() as conn:
        count = conn.execute(text("SELECT count(*) FROM dwh.fact_hr WHERE src_system = :s"),
                             {"s": source}).scalar_one()
        branch_id = conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                 {"c": a["code"]}).scalar_one()
        fact = conn.execute(text(
            "SELECT sum(headcount_fact) FROM mart.agg_hr_month WHERE build_id = :b "
            "AND branch_id = :br AND month_id = 202609"),
            {"b": result.build_id, "br": branch_id}).scalar_one()
    assert count == 3 and float(fact) == 90.0


@pytest.fixture
def orgs_setting() -> Iterator[None]:
    yield
    put_setting("hr.orgs", [])
    clear_setting("hr.base_url")
    with get_engine("app").begin() as conn:
        integrations.clear_secret(conn, "hr.username")
        integrations.clear_secret(conn, "hr.password")


def test_hr_orgs_cli_make_connector_and_worker(tmp_path: Path, orgs_setting: None,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    good = tmp_path / "orgs.json"
    good.write_text(json.dumps([o.model_dump() for o in ORGS], ensure_ascii=False),
                    encoding="utf-8")
    assert cli.main(["hr-orgs", "--file", str(good)]) == 0
    with get_engine("app").connect() as conn:
        assert current_setting(conn, "hr.orgs") == [o.model_dump() for o in ORGS]
    with get_engine("migrator").connect() as conn:
        details = conn.execute(text(
            "SELECT details FROM core.audit_log WHERE action = 'admin.setting.updated' "
            "ORDER BY id DESC LIMIT 1")).scalar_one()
    assert details["via"] == "cli" and details["orgs"] == 2
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"org": "X", "branch_code": "NOPE"}]), encoding="utf-8")
    assert cli.main(["hr-orgs", "--file", str(bad)]) == 1
    assert cli.main(["hr-orgs"]) == 0
    assert "NOPE" in capsys.readouterr().out
    assert {"hr", "mehnat"} <= set(KNOWN_SOURCES)
    with pytest.raises(ConfigError, match=r"hr\.base_url"):
        make_connector("hr", get_settings())
    put_setting("hr.base_url", "https://hr.test")
    with pytest.raises(ConfigError, match=r"hr\.username"):
        make_connector("hr", get_settings())
    with get_engine("app").begin() as conn:
        integrations.store_secret(conn, "hr.username", "u", None)
        integrations.store_secret(conn, "hr.password", "p", None)
    made = make_connector("hr", get_settings())
    assert isinstance(made, HrConnector) and [o.org for o in made.orgs] == [o.org for o in ORGS]
    with pytest.raises(ConfigError, match=r"mehnat\.uz"):
        make_connector("mehnat", get_settings())
    with get_engine("app").connect() as conn:
        assert integrations.configured(conn, "hr") is True
    jobs = {j.id: j for j in worker.build_scheduler(get_settings(), RecordingNotifier()).get_jobs()}
    assert jobs["etl_hr"].func is worker.run_hr_job


def test_hr_job_skips_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(worker, "run_etl_job", lambda *_a: called.append("run"))
    assert worker.run_hr_job(RecordingNotifier()) is None and called == []
    assert cli.main(["hr-check"]) == 2


def test_hr_notification_only_for_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.etl.runner import RunResult

    source = new_source()
    run = open_run(source)
    monkeypatch.setattr(worker, "run_etl_job", lambda *_a: RunResult(run, "success", None))
    monkeypatch.setattr(integrations, "configured", lambda *_a: True)
    notifier = RecordingNotifier()
    with etl_transaction() as conn:
        DbStagingSink(conn, run, source).error(target="hr_api", code="no_branch_breakdown",
                                               message="m", severity="warning")
    worker.run_hr_job(notifier)
    assert notifier.kinds == []
    with etl_transaction() as conn:
        DbStagingSink(conn, run, source).error(target="hr_api", code="unmapped_org",
                                               message="m")
    worker.run_hr_job(notifier)
    assert notifier.kinds == ["hr_rows_rejected"]
