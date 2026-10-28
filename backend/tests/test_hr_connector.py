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
from app.etl.hr.models import parse_structure, parse_total
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
ORGS = [HrOrg(org="Название не важно", branch_code="UGE-02", hr_id=6),
        HrOrg(org="quyi  bo?zsuv GES", branch_code="UGE-12"),  # id yo'q — nom bo'yicha
        HrOrg(org="O'zbekgidroenergo AJ", branch_code="UGE-01", hr_id=1)]


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

    def __init__(self) -> None:
        data = json.loads((FIXTURES / "structure.json").read_text(encoding="utf-8"))
        self.rows = tuple(parse_structure(data))
        self.total = parse_total(data)

    def healthcheck(self) -> HealthResult:
        return HealthResult(True, "fake")

    def snapshot(self, today: date) -> HrSnapshot:
        return HrSnapshot(today, self.rows, self.total)


def _extract(source: FakeSource, orgs: list[HrOrg] = ORGS) -> ReportSink:
    sink = ReportSink()
    HrConnector(source, orgs, today=lambda: TEST_AS_OF).extract(WINDOW, sink)
    return sink


def test_structure_is_mapped_by_id_then_name(caplog: pytest.LogCaptureFixture,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    caplog.set_level(logging.DEBUG)
    sink = _extract(FakeSource())
    facts = {r["src_id"]: r for t, r in sink.rows if t == "fact_hr"}
    lead, work, none = (position_code(c) for c in ("Руководители", "Рабочие", "Без категории"))
    assert set(facts) == {f"UGE-01:{lead}:202609", f"UGE-01:{position_code('Специалисты')}:202609",
                          f"UGE-01:{none}:202609", f"UGE-02:{work}:202609",
                          f"UGE-02:{position_code('Служащие')}:202609", f"UGE-12:{work}:202609"}
    row = facts[f"UGE-02:{work}:202609"]
    assert (row["date_id"], row["headcount_plan"], row["headcount_fact"], row["hired"],
            row["fired"], row["overtime_hours"], row["payroll"]) == (20260924, 0, 35, 0, 0, 0, 0)
    positions = {r["code"]: r for t, r in sink.rows if t == "dim_position"}
    assert positions[lead] == {"code": lead, "category": "Руководители", "department": "—"}
    assert [(c, s) for _, c, _, s in sink.errors] == [("unmapped_org", "warning")]
    assert "1 орг." in sink.errors[0][2] and "25" in sink.errors[0][2]  # id, nom emas
    assert "UGE-JINLUN" not in sink.errors[0][2]
    everything = json.dumps([sink.rows, sink.errors], ensure_ascii=False, default=str)
    captured = capsys.readouterr()
    for secret in ("Иванов", "Boshqaruv"):
        assert secret not in everything and secret not in caplog.text
        assert secret not in captured.out and secret not in captured.err


def test_id_wins_over_a_wrong_name() -> None:
    clash = [HrOrg(org="O'zbekgidroenergo AJ", branch_code="UGE-09"),
             HrOrg(org="x", branch_code="UGE-01", hr_id=1)]
    sink = _extract(FakeSource(), clash)
    assert {r["branch_code"] for t, r in sink.rows if t == "fact_hr"} == {"UGE-01"}


def test_requires_reporting_sink() -> None:
    class Plain:
        def add(self, target: str, row: Mapping[str, Any]) -> None: ...

    with pytest.raises(TypeError):
        HrConnector(FakeSource(), ORGS).extract(WINDOW, Plain())


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
    orgs = [HrOrg(org="x", branch_code=a["code"], hr_id=6),
            HrOrg(org="y", branch_code=b["code"], hr_id=10),
            HrOrg(org="Неизвестный филиал", branch_code=b["code"])]
    for _ in range(2):
        connector = HrConnector(FakeSource(), orgs, source_name=source,
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
    assert count == 3 and float(fact) == 40.0


@pytest.fixture
def orgs_setting() -> Iterator[None]:
    yield
    put_setting("hr.orgs", [])
    clear_setting("hr.base_url")
    with get_engine("app").begin() as conn:
        integrations.clear_secret(conn, "hr.api_key")


def test_hr_orgs_cli_make_connector_and_worker(tmp_path: Path, orgs_setting: None,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    good = tmp_path / "orgs.json"
    good.write_text(json.dumps([o.model_dump(exclude_none=True) for o in ORGS],
                               ensure_ascii=False),
                    encoding="utf-8")
    assert cli.main(["hr-orgs", "--file", str(good)]) == 0
    with get_engine("app").connect() as conn:
        assert current_setting(conn, "hr.orgs") == [o.model_dump(exclude_none=True) for o in ORGS]
    with get_engine("migrator").connect() as conn:
        details = conn.execute(text(
            "SELECT details FROM core.audit_log WHERE action = 'admin.setting.updated' "
            "ORDER BY id DESC LIMIT 1")).scalar_one()
    assert details["via"] == "cli" and details["orgs"] == 3
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"org": "X", "branch_code": "NOPE"}]), encoding="utf-8")
    assert cli.main(["hr-orgs", "--file", str(bad)]) == 1
    assert cli.main(["hr-orgs"]) == 0
    assert "NOPE" in capsys.readouterr().out
    assert {"hr", "mehnat"} <= set(KNOWN_SOURCES)
    put_setting("hr.base_url", "")
    with pytest.raises(ConfigError, match=r"hr\.base_url"):
        make_connector("hr", get_settings())
    put_setting("hr.base_url", "https://hr.test")
    with pytest.raises(ConfigError, match=r"hr\.api_key"):
        make_connector("hr", get_settings())
    with get_engine("app").begin() as conn:
        integrations.store_secret(conn, "hr.api_key", "k", None)
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
        DbStagingSink(conn, run, source).error(target="hr_api", code="unmapped_org",
                                               message="m", severity="warning")
    worker.run_hr_job(notifier)
    assert notifier.kinds == []
    with etl_transaction() as conn:
        DbStagingSink(conn, run, source).error(target="hr_api", code="unmapped_org",
                                               message="m")
    worker.run_hr_job(notifier)
    assert notifier.kinds == ["hr_rows_rejected"]


def test_name_fallback_only_for_entries_without_hr_id() -> None:
    orgs = [HrOrg(org="Quyi Bo?zsuv GES", branch_code="UGE-12", hr_id=99)]
    sink = _extract(FakeSource(), orgs)  # nom mos, lekin yozuvda hr_id bor -> nom bo'yicha emas
    assert [t for t, _ in sink.rows if t == "fact_hr"] == []
