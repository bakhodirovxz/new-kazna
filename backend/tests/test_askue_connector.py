import json
import os
import time
from collections.abc import Iterator, Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app import cli, worker
from app.core.config import ConfigError, get_settings
from app.core.db import get_engine
from app.dwh import builds
from app.dwh.reference import current_setting
from app.etl.askue.connector import AskueConnector, to_mln_kwh
from app.etl.askue.export import ExportFile
from app.etl.askue.registry import AskueStation
from app.etl.connectors import KNOWN_SOURCES, make_connector
from app.etl.db import etl_transaction
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
from tests.helpers import put_setting

FIXTURE = Path(__file__).parent / "fixtures" / "askue" / "askue_2026-09-23.csv"
WINDOW = Window(date(2026, 9, 1), TEST_AS_OF)
STATIONS = [AskueStation(code="CHARVAK-1", name="Chorvoq GES", branch_code="UGE-02"),
            AskueStation(code="CHIRCHIQ-7", name="Chirchiq GES-7", branch_code="UGE-03")]


class ReportSink:
    def __init__(self) -> None:
        self.load_id = 0
        self.rows: list[tuple[str, dict[str, Any]]] = []
        self.errors: list[tuple[str, str, str]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))

    def error(self, *, target: str, code: str, message: str, src_id: str | None = None,
              severity: str = "error") -> None:
        self.errors.append((target, code, message))


class ListExport:
    name = "list"

    def __init__(self, *files: ExportFile) -> None:
        self._files = files

    def healthcheck(self) -> HealthResult:
        return HealthResult(True, "list")

    def files(self, window: Window) -> Iterator[ExportFile]:
        yield from self._files


def _extract(*files: ExportFile, stations: list[AskueStation] = STATIONS,
             window: Window = WINDOW) -> ReportSink:
    sink = ReportSink()
    AskueConnector(ListExport(*files), stations, today=lambda: TEST_AS_OF).extract(window, sink)
    return sink


def test_units_and_mapping() -> None:
    assert to_mln_kwh(Decimal("4810.6")) == Decimal("4.811")
    sink = _extract(ExportFile("a.csv", FIXTURE.read_bytes()))
    assert sink.errors == []
    rows = [r for _, r in sink.rows]
    assert [(r["src_id"], r["branch_code"], r["generation"], r["own_needs"], r["supply"])
            for r in rows] == [
        ("CHARVAK-1:20260922", "UGE-02", Decimal("4.811"), Decimal("0.072"), Decimal("4.738")),
        ("CHARVAK-1:20260923", "UGE-02", Decimal("4.702"), Decimal("0.070"), Decimal("4.632")),
        ("CHIRCHIQ-7:20260923", "UGE-03", Decimal("1.320"), Decimal("0.020"), Decimal("1.300")),
    ]
    assert all(r["doc_type"] == "askue_daily" and r["plan"] is None for r in rows)
    assert rows[1]["work_hours"] == Decimal("23.5") and rows[0]["date_id"] == 20260922


def test_unknown_station_is_reported() -> None:
    sink = _extract(ExportFile("a.csv", FIXTURE.read_bytes()), stations=STATIONS[:1])
    assert len(sink.rows) == 2
    assert [(t, c) for t, c, _ in sink.errors] == [("askue_file", "unknown_station")]
    assert "a.csv:4" in sink.errors[0][2] and "CHIRCHIQ-7" in sink.errors[0][2]


def test_bad_rows_are_reported_not_fatal() -> None:
    header = b"station;date;generation_mwh;own_needs_mwh;supply_mwh;work_hours\n"
    sink = _extract(ExportFile("bad.csv", b"not;a;header\n1;2;3"),
                    ExportFile("big.csv", b"", "too_large"),
                    ExportFile("rows.csv", header + b"CHARVAK-1;2026-09-20;-1;0;;\n"
                                                    b"CHARVAK-1;2026-09-21;100;1;;\n"))
    assert [c for _, c, _ in sink.errors] == ["bad_header", "too_large", "negative"]
    assert [r["src_id"] for _, r in sink.rows] == ["CHARVAK-1:20260921"]
    assert all(msg.startswith(("bad.csv", "big.csv", "rows.csv:2")) for _, _, msg in sink.errors)


def test_rows_outside_window_are_skipped() -> None:
    sink = _extract(ExportFile("a.csv", FIXTURE.read_bytes()),
                    window=Window(date(2026, 9, 23), TEST_AS_OF))
    assert [r["date_id"] for _, r in sink.rows] == [20260923, 20260923]


def test_requires_reporting_sink() -> None:
    class Plain:
        def add(self, target: str, row: Mapping[str, Any]) -> None: ...

    with pytest.raises(TypeError):
        AskueConnector(ListExport(), STATIONS).extract(WINDOW, Plain())


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def _inbox(tmp_path: Path, content: bytes) -> Path:
    inbox = tmp_path / "askue"
    inbox.mkdir()
    path = inbox / "askue_2026-09-23.csv"
    path.write_bytes(content)
    old = time.time() - 3600
    os.utime(path, (old, old))
    return inbox


def _test_branches(source: str, capacity: float) -> tuple[str, str]:
    tag = new_tag()
    a, b = branch_row(tag, capacity_mw=capacity), branch_row(f"{tag}B", capacity_mw=capacity)
    run = open_run(source)
    stage(run, source, {"dim_branch": [a, b]})
    merge_all(run, source)
    return a["code"], b["code"]


def _stations(a: str, b: str) -> list[AskueStation]:
    return [AskueStation(code="CHARVAK-1", name="Chorvoq GES", branch_code=a),
            AskueStation(code="CHIRCHIQ-7", name="Chirchiq GES-7", branch_code=b)]


def test_runner_loads_idempotently(source: str, tmp_path: Path) -> None:
    from app.etl.askue.export import DirectoryExport

    a, b = _test_branches(source, capacity=300)  # 300 × 24 = 7200 MVt·soat ≥ 4810,6
    inbox = _inbox(tmp_path, FIXTURE.read_bytes())
    for _ in range(2):
        connector = AskueConnector(DirectoryExport(inbox), _stations(a, b), source=source,
                                   today=lambda: TEST_AS_OF)
        result = Runner(connector, mode=Mode.INCREMENTAL, today=TEST_AS_OF,
                        sleep=lambda _: None).run()
        assert result.status == "success", result
    with etl_transaction() as conn:
        rows = conn.execute(text("SELECT src_id, generation FROM dwh.fact_generation "
                                 "WHERE src_system = :s ORDER BY src_id"), {"s": source}).all()
    assert [(r.src_id, r.generation) for r in rows] == [
        ("CHARVAK-1:20260922", Decimal("4.811")), ("CHARVAK-1:20260923", Decimal("4.702")),
        ("CHIRCHIQ-7:20260923", Decimal("1.320"))]


def test_runner_rejects_generation_above_capacity(source: str, tmp_path: Path) -> None:
    from app.etl.askue.export import DirectoryExport

    a, b = _test_branches(source, capacity=100)  # 100 × 24 = 2400 MVt·soat < 4810,6
    with etl_transaction() as conn:
        before = builds.active_build(conn)
    connector = AskueConnector(DirectoryExport(_inbox(tmp_path, FIXTURE.read_bytes())),
                               _stations(a, b), source=source, today=lambda: TEST_AS_OF)
    result = Runner(connector, mode=Mode.INCREMENTAL, today=TEST_AS_OF,
                    sleep=lambda _: None).run()
    assert result.status == "failed_quality"
    with etl_transaction() as conn:
        assert builds.active_build(conn) == before
        detail = conn.execute(text("SELECT detail FROM core.etl_step WHERE run_id = :r "
                                   "AND name = 'quality'"), {"r": result.run_id}).scalar_one()
    assert detail["capacity_limit"]["ok"] is False


@pytest.fixture
def stations_setting() -> Iterator[None]:
    yield
    put_setting("askue.stations", [])


def test_askue_stations_cli_and_make_connector(tmp_path: Path, stations_setting: None,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    good = tmp_path / "stations.json"
    good.write_text(json.dumps([s.model_dump() for s in STATIONS], ensure_ascii=False),
                    encoding="utf-8")
    assert cli.main(["askue-stations", "--file", str(good)]) == 0
    with get_engine("app").connect() as conn:
        assert current_setting(conn, "askue.stations") == [s.model_dump() for s in STATIONS]
    with get_engine("migrator").connect() as conn:
        details = conn.execute(text(
            "SELECT details FROM core.audit_log WHERE action = 'admin.setting.updated' "
            "ORDER BY id DESC LIMIT 1")).scalar_one()
    assert details["via"] == "cli" and details["stations"] == 2
    assert cli.main(["askue-stations"]) == 0
    hq = tmp_path / "hq.json"
    hq.write_text(json.dumps([{"code": "X-1", "name": "X", "branch_code": "UGE-01"}]),
                  encoding="utf-8")
    assert cli.main(["askue-stations", "--file", str(hq)]) == 1
    unknown = tmp_path / "unknown.json"
    unknown.write_text(json.dumps([{"code": "X-1", "name": "X", "branch_code": "NOPE"}]),
                       encoding="utf-8")
    assert cli.main(["askue-stations", "--file", str(unknown)]) == 1
    out = capsys.readouterr().out
    assert "CHARVAK-1" in out and "UGE-01" in out and "NOPE" in out
    assert "askue" in KNOWN_SOURCES
    made = make_connector("askue", get_settings().model_copy(
        update={"askue_inbox_dir": str(tmp_path)}))
    assert isinstance(made, AskueConnector) and [s.code for s in made.stations] == [
        "CHARVAK-1", "CHIRCHIQ-7"]
    put_setting("askue.stations", [])
    with pytest.raises(ConfigError, match=r"askue\.stations"):
        make_connector("askue", get_settings())


def test_notify_askue_errors() -> None:
    source = new_source()
    run = open_run(source)
    notifier = RecordingNotifier()
    assert worker.notify_askue_errors(run, notifier) == 0 and notifier.items == []
    with etl_transaction() as conn:
        sink = DbStagingSink(conn, run, source)
        for code in ("unknown_station", "negative", "negative"):
            sink.error(target="askue_file", code=code, message="m")
    assert worker.notify_askue_errors(run, notifier) == 3
    assert notifier.kinds == ["askue_rows_rejected"]
    body = notifier.items[0].body
    assert "negative: 2" in body and "unknown_station: 1" in body
