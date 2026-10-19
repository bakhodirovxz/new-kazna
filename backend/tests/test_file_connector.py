import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import structlog
from sqlalchemy import text

from app.core.config import ConfigError, get_settings
from app.etl.connectors import make_connector
from app.etl.db import etl_transaction
from app.etl.file_connector import FileConnector
from app.etl.runner import Runner, RunResult
from app.etl.types import Mode
from tests.etl_helpers import TEST_AS_OF, new_source, new_tag, purge_source

HEADER = "doc_type;src_id;date;branch_code;item_code;direction;amount"


@pytest.fixture(autouse=True)
def _plain_logs() -> Iterator[None]:
    # Sozlanmagan structlog dev-renderi rich traceback bilan (xavfsiz xato turi uchun exc_info)
    # osilib qoladi -- prod'dagi kabi JSON renderi.
    structlog.configure(processors=[structlog.processors.format_exc_info,
                                    structlog.processors.JSONRenderer()])
    yield
    structlog.reset_defaults()


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def _write(path: Path, lines: list[str], *, bom: bool = False) -> None:
    path.write_text(("\ufeff" if bom else "") + "\n".join(lines) + "\n", encoding="utf-8")


def _branch(directory: Path, tag: str) -> str:
    _write(directory / "dim_branch.csv",
           ["code;name;short_name;kind;capacity_mw;sort_order",
            f"T-{tag};Тестовая ГЭС;Т;ges;12,5;99"])
    return f"T-{tag}"


def _run(directory: Path, source: str, sleeps: list[float] | None = None) -> RunResult:
    return Runner(FileConnector(directory, source=source), mode=Mode.FULL, today=TEST_AS_OF,
                  sleep=(sleeps if sleeps is not None else []).append).run()


def test_csv_load_end_to_end(tmp_path: Path, source: str) -> None:
    code = _branch(tmp_path, new_tag())
    _write(tmp_path / "fact_cashflow.csv", [
        HEADER,
        f"bank_entry;f1;2026-08-05;{code};PKM54-O09;out;1234.50",
        f"bank_entry;f2;2026-08-06;{code};PKM54-O09;out;10,25",
        f"bank_entry;old;2023-01-01;{code};PKM54-O09;out;5",
    ], bom=True)
    _write(tmp_path / "control_totals.csv", ["month;amount", "202608;1244.75"])
    result = _run(tmp_path, source)
    assert result.status == "success", result
    with etl_transaction() as conn:
        rows = conn.execute(text(
            "SELECT src_id, date_id, amount FROM dwh.fact_cashflow WHERE src_system = :s "
            "ORDER BY src_id"), {"s": source}).all()
        capacity = conn.execute(text("SELECT capacity_mw FROM dwh.dim_branch WHERE code = :c"),
                                {"c": code}).scalar_one()
    assert [(r[0], r[1], float(r[2])) for r in rows] == [
        ("f1", 20260805, 1234.5), ("f2", 20260806, 10.25)]
    assert float(capacity) == 12.5


def test_thousands_separator_fails_without_retry(tmp_path: Path, source: str) -> None:
    code = _branch(tmp_path, new_tag())
    _write(tmp_path / "fact_cashflow.csv",
           [HEADER, f"bank_entry;f1;2026-08-05;{code};PKM54-O09;out;1 234,50"])
    sleeps: list[float] = []
    result = _run(tmp_path, source, sleeps)
    assert result.status == "failed" and sleeps == []
    assert "разделитель разрядов" in (result.error or "")
    assert "fact_cashflow.csv:2" in (result.error or "")


def test_inn_with_spaces_is_not_a_number_error(tmp_path: Path, source: str) -> None:
    _write(tmp_path / "dim_counterparty.csv",
           ["code;name;kind;inn", f"CP-{new_tag()};ООО «Тест»;supplier;305 123 456"])
    assert _run(tmp_path, source).status == "success"


def test_bad_date_fails(tmp_path: Path, source: str) -> None:
    code = _branch(tmp_path, new_tag())
    _write(tmp_path / "fact_cashflow.csv",
           [HEADER, f"bank_entry;f1;05.08.2026;{code};PKM54-O09;out;1"])
    result = _run(tmp_path, source)
    assert result.status == "failed" and "неверная дата" in (result.error or "")


def test_non_utf8_file_fails(tmp_path: Path, source: str) -> None:
    (tmp_path / "dim_branch.csv").write_bytes(
        "code;name;short_name;kind\nT-1;Тест;Т;ges\n".encode("cp1251"))
    result = _run(tmp_path, source)
    assert result.status == "failed" and "UTF-8" in (result.error or "")


def test_missing_directory_is_unavailable(tmp_path: Path, source: str) -> None:
    missing = tmp_path / "nope"
    assert FileConnector(missing).healthcheck().ok is False
    sleeps: list[float] = []
    result = _run(missing, source, sleeps)
    assert result.status == "failed" and len(sleeps) == 3


def test_watermark_is_newest_file_mtime(tmp_path: Path) -> None:
    connector = FileConnector(tmp_path)
    assert connector.watermark().value is None
    _write(tmp_path / "dim_item.csv", ["code;name;activity;direction"])
    os.utime(tmp_path / "dim_item.csv", (1_790_000_000, 1_790_000_000))
    assert connector.watermark().value == datetime.fromtimestamp(1_790_000_000, tz=UTC)


def test_make_connector_rules(tmp_path: Path) -> None:
    prod = get_settings().model_copy(update={"env": "prod"})
    with pytest.raises(ConfigError):
        make_connector("synthetic", prod)
    with pytest.raises(ValueError, match="noma'lum manba"):
        make_connector("oracle")
    dev = get_settings().model_copy(update={"env": "dev", "etl_file_dir": str(tmp_path)})
    assert isinstance(make_connector("file", dev), FileConnector)
    assert make_connector("synthetic", dev).source == "synthetic"


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", "1e5", "1e400", "0x10"])
def test_non_plain_numbers_rejected_without_retry(tmp_path: Path, source: str, bad: str) -> None:
    code = _branch(tmp_path, new_tag())
    _write(tmp_path / "fact_cashflow.csv",
           [HEADER, f"bank_entry;f1;2026-08-05;{code};PKM54-O09;out;{bad}"])
    sleeps: list[float] = []
    result = _run(tmp_path, source, sleeps)
    assert result.status == "failed" and sleeps == []
    assert "неверное число" in (result.error or "")


def test_raw_values_do_not_leak_via_cause_chain(tmp_path: Path) -> None:
    import traceback

    from app.etl.types import Window
    from tests.etl_helpers import FULL_WINDOW

    class Sink:
        def add(self, target: str, row: object) -> None: ...

    cases = {
        "fact_cashflow.csv": ([HEADER, "bank_entry;f1;05.08.2026;X;PKM54-O09;out;1"], "05.08.2026"),
        "dim_branch.csv": (["code;name;short_name;kind;capacity_mw", "X;a;b;ges;SECRET9"],
                           "SECRET9"),
    }
    window: Window = FULL_WINDOW
    for name, (lines, secret) in cases.items():
        directory = tmp_path / name
        directory.mkdir()
        _write(directory / name, lines)
        with pytest.raises(ValueError) as info:
            FileConnector(directory).extract(window, Sink())  # type: ignore[arg-type]
        assert secret not in "".join(traceback.format_exception(info.value))
    (tmp_path / "enc").mkdir()
    (tmp_path / "enc" / "dim_branch.csv").write_bytes(
        "code;name\nT;Тест\n".encode("cp1251"))
    with pytest.raises(ValueError) as info:
        FileConnector(tmp_path / "enc").extract(window, Sink())  # type: ignore[arg-type]
    assert "xd2" not in "".join(traceback.format_exception(info.value))
    assert info.value.__cause__ is None
