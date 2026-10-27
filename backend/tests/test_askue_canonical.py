import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.etl.askue import canonical
from app.etl.askue.canonical import AskueFileError, parse_canonical
from app.etl.askue.export import (
    AskueApiExport,
    AskueNotConfigured,
    DirectoryExport,
)
from app.etl.types import ConnectorUnavailableError, Window

FIXTURE = Path(__file__).parent / "fixtures" / "askue" / "askue_2026-09-23.csv"
TODAY = date(2026, 9, 24)
HEADER = "station;date;generation_mwh;own_needs_mwh;supply_mwh;work_hours"
WINDOW = Window(date(2026, 9, 1), TODAY)


def _parse(*lines: str) -> canonical.ParsedAskue:
    return parse_canonical("\n".join((HEADER, *lines)).encode("utf-8"), today=TODAY)


def test_fixture_parses_with_optional_fields() -> None:
    parsed = parse_canonical(FIXTURE.read_bytes(), today=TODAY)
    assert parsed.errors == ()
    first, second, third = parsed.rows
    assert (first.station, first.day, first.generation, first.own_needs, first.supply,
            first.work_hours) == ("CHARVAK-1", date(2026, 9, 22), Decimal("4810.6"),
                                  Decimal("72.2"), Decimal("4738.4"), Decimal("24"))
    assert second.supply is None and second.work_hours == Decimal("23.5")
    assert third.line == 4 and third.generation == Decimal("1320.25")


def test_bom_and_blank_lines_are_accepted() -> None:
    data = ("\ufeff" + HEADER + "\n\nA-1;2026-09-20;10;1;;\n").encode("utf-8")
    parsed = parse_canonical(data, today=TODAY)
    assert [r.station for r in parsed.rows] == ["A-1"] and parsed.errors == ()


@pytest.mark.parametrize(("data", "code"), [
    (b"station;date;generation;own;supply;hours\nA;2026-09-20;1;0;;", "bad_header"),
    (f"{HEADER}\nСтанция;2026-09-20;1;0;;".encode("cp1251"), "bad_encoding"),
    (b"", "bad_header"),
])
def test_file_level_errors(data: bytes, code: str) -> None:
    with pytest.raises(AskueFileError) as exc:
        parse_canonical(data, today=TODAY)
    assert exc.value.code == code


def test_row_errors_do_not_stop_parsing() -> None:
    parsed = _parse(
        "A-1;2026-09-20;100;2;98;24",
        "A-1;2026-09-20;100;2;98;24",  # takror
        "A-2;20.09.2026;100;2;;",  # sana formati
        "A-3;2026-09-20;1 000;2;;",  # razryad ajratkichi
        "A-4;2026-09-20;-5;0;;",
        "A-5;2026-09-20;10;12;;",
        "A-6;2026-09-20;10;1;;25",
        "A-7;2026-09-25;10;1;;",
        "bad code;2026-09-20;10;1;;",
        "A-8;2026-09-20;10;1",
        "A-9;2026-09-21;10,5;1;;",
    )
    assert [r.station for r in parsed.rows] == ["A-1"]
    assert [(e.line, e.code) for e in parsed.errors] == [
        (3, "duplicate_row"), (4, "bad_row"), (5, "bad_row"), (6, "negative"),
        (7, "own_gt_generation"), (8, "bad_hours"), (9, "future_date"), (10, "bad_row"),
        (11, "bad_row"), (12, "bad_row")]


def test_too_many_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(canonical, "MAX_ROWS", 2)
    with pytest.raises(AskueFileError) as exc:
        _parse("A-1;2026-09-20;1;0;;", "A-1;2026-09-21;1;0;;", "A-1;2026-09-22;1;0;;")
    assert exc.value.code == "too_many_rows"


def test_directory_export_filters_files(tmp_path: Path) -> None:
    now = 1_790_000_000.0
    files = {"ok.csv": now - 3600, "fresh.csv": now - 10, "old.csv": now - 9 * 86400,
             "note.txt": now - 3600, "big.csv": now - 3600}
    for name, mtime in files.items():
        path = tmp_path / name
        path.write_bytes(b"x" * (2000 if name == "big.csv" else 10))
        os.utime(path, (mtime, mtime))
    (tmp_path / "link.csv").symlink_to(tmp_path / "ok.csv")
    export = DirectoryExport(tmp_path, max_age_days=7, max_bytes=1000, now=lambda: now)
    got = {(f.name, f.error) for f in export.files(WINDOW)}
    assert got == {("ok.csv", None), ("big.csv", "too_large")}
    assert export.healthcheck().ok is True
    missing = DirectoryExport(tmp_path / "nope")
    assert missing.healthcheck().ok is False
    with pytest.raises(ConnectorUnavailableError):
        list(missing.files(WINDOW))


def test_api_export_is_not_configured() -> None:
    with pytest.raises(AskueNotConfigured, match="АСКУЭ API не настроен"):
        AskueApiExport()


def test_csv_error_is_a_file_level_error() -> None:
    data = (HEADER + '\n"' + "A" * 200_000).encode("utf-8")  # muvozanatsiz qo'shtirnoq
    with pytest.raises(AskueFileError) as exc:
        parse_canonical(data, today=TODAY)
    assert exc.value.code == "bad_csv"
