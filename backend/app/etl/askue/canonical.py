"""АСКУЭ kunlik eksportining kanonik CSV formati (docs/integration/askue-format.md;
TZ 8 «Общие правила обмена»: UTF-8, «;», ISO sanalar, nuqta, razryad ajratkichsiz).

station;date;generation_mwh;own_needs_mwh;supply_mwh;work_hours — stansiya × sutka, MVt·soat.
Fayl darajasidagi xato (kodlash, sarlavha, hajm) — AskueFileError; qator xatolari yig'iladi,
yaroqli qatorlar qaytariladi. Xato matnlarida faqat qator raqami va qisqa maydon qiymati.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

COLUMNS = ("station", "date", "generation_mwh", "own_needs_mwh", "supply_mwh", "work_hours")
MAX_ROWS = 100_000
_NUM = re.compile(r"^\d{1,9}(\.\d{1,3})?$")
_NEG = re.compile(r"^-\d")
_HOURS = re.compile(r"^\d{1,2}(\.\d{1,2})?$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_STATION = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")


class AskueFileError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class AskueRow:
    line: int
    station: str
    day: date
    generation: Decimal  # MVt·soat
    own_needs: Decimal
    supply: Decimal | None
    work_hours: Decimal | None


@dataclass(frozen=True, slots=True)
class RowError:
    line: int
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ParsedAskue:
    rows: tuple[AskueRow, ...]
    errors: tuple[RowError, ...]


class _ProblemError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _amount(value: str, field: str) -> Decimal:
    if _NEG.match(value):
        raise _ProblemError("negative", f"{field}: отрицательное значение")
    if not _NUM.fullmatch(value):
        raise _ProblemError("bad_row", f"{field}: ожидается число с точкой, без разделителей")
    return Decimal(value)


def _row(line: int, fields: list[str], today: date) -> AskueRow:
    station, day_s, gen_s, own_s, sup_s, hrs_s = (f.strip() for f in fields)
    if not _STATION.fullmatch(station):
        raise _ProblemError("bad_row", f"код станции «{station[:40]}» недопустим")
    try:
        if not _DATE.fullmatch(day_s):
            raise ValueError(day_s)
        day = date.fromisoformat(day_s)
    except ValueError as exc:
        raise _ProblemError("bad_row", f"дата «{day_s[:20]}»: нужен формат ГГГГ-ММ-ДД") from exc
    if day > today:
        raise _ProblemError("future_date", f"дата {day:%d.%m.%Y} в будущем")
    generation = _amount(gen_s, "generation_mwh")
    own = _amount(own_s, "own_needs_mwh")
    if own > generation:
        raise _ProblemError("own_gt_generation", "собственные нужды больше выработки")
    supply = _amount(sup_s, "supply_mwh") if sup_s else None
    hours: Decimal | None = None
    if hrs_s:
        if not _HOURS.fullmatch(hrs_s) or Decimal(hrs_s) > 24:
            raise _ProblemError("bad_hours", "work_hours: от 0 до 24")
        hours = Decimal(hrs_s)
    return AskueRow(line, station, day, generation, own, supply, hours)


def parse_canonical(data: bytes, *, today: date) -> ParsedAskue:
    try:
        return _parse(data, today)
    except csv.Error as exc:  # masalan: maydon limiti (muvozanatsiz qo'shtirnoq)
        raise AskueFileError("bad_csv", "файл не разбирается как CSV") from exc


def _parse(data: bytes, today: date) -> ParsedAskue:
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AskueFileError("bad_encoding", "файл не в кодировке UTF-8") from exc
    reader = csv.reader(io.StringIO(content, newline=""), delimiter=";")
    header = next(reader, None)
    if header is None or tuple(h.strip().lower() for h in header) != COLUMNS:
        raise AskueFileError("bad_header", f"заголовок должен быть «{';'.join(COLUMNS)}»")
    rows: list[AskueRow] = []
    errors: list[RowError] = []
    seen: set[tuple[str, date]] = set()
    for line, raw in enumerate(reader, start=2):
        if not raw or all(not cell.strip() for cell in raw):
            continue
        if len(rows) + len(errors) >= MAX_ROWS:
            raise AskueFileError("too_many_rows", f"в файле больше {MAX_ROWS} строк")
        if len(raw) != len(COLUMNS):
            errors.append(RowError(line, "bad_row", "неверное число полей"))
            continue
        try:
            row = _row(line, raw, today)
        except _ProblemError as problem:
            errors.append(RowError(line, problem.code, problem.message))
            continue
        key = (row.station, row.day)
        if key in seen:
            errors.append(RowError(line, "duplicate_row",
                                   f"{row.station} {row.day:%d.%m.%Y}: повтор строки"))
            continue
        seen.add(key)
        rows.append(row)
    return ParsedAskue(tuple(rows), tuple(errors))
