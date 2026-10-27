"""«Ввод данных»: kanonik shablonlar va CSV/XLSX import. Fayl diskka yozilmaydi; hammasi yoki
hech narsa. Xato elementi: {"row": fayl qatori (1 = sarlavha), "field", "code"} -- QIYMATSIZ."""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.errors import ValidationFailed
from app.etl.errors import FileFormatError
from app.etl.file_connector import _number
from app.manual.entities import FieldDef, ManualEntity

CSV_TYPE = "text/csv"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_ROWS = 5000
MAX_ERRORS = 200
ZIP_MAX_MEMBERS = 100
ZIP_MAX_BYTES = 20 * 1024 * 1024
_NUMERIC = frozenset({"money", "volume", "int", "decimal", "pct"})
_BAD_ZIP = ("xl/vbaProject.bin", "xl/externalLinks/")
_KIND_RU = {"money": "сумма", "volume": "число", "int": "целое", "decimal": "число",
            "pct": "процент", "date": "дата ГГГГ-ММ-ДД", "month": "месяц ГГГГ-ММ",
            "text": "текст", "enum": "значение из списка", "ref": "код из справочника",
            "secret": "текст (скрыто)"}
Rows = list[tuple[int, list[Any]]]


def _unsupported() -> ValidationFailed:
    return ValidationFailed("unsupported_file")


def _invalid(rows: list[dict[str, Any]]) -> ValidationFailed:
    return ValidationFailed("import_invalid", rows=rows[:MAX_ERRORS],
                            fields=sorted({r["field"] for r in rows}))


def _safe(value: str) -> str:
    """Formula-injection: `=+-@` yoki TAB/CR bilan boshlangan matn `'` bilan."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def template_csv(entity: ManualEntity) -> bytes:
    out = io.StringIO()
    csv.writer(out, delimiter=";", lineterminator="\r\n").writerow(
        [_safe(f.name) for f in entity.fields])
    return b"\xef\xbb\xbf" + out.getvalue().encode()


def template_xlsx(entity: ManualEntity) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    data = wb.active
    assert data is not None
    data.title = "Данные"
    data.append([_safe(f.name) for f in entity.fields])
    info = wb.create_sheet("Описание")
    info.append(["Колонка", "Название", "Тип", "Обязательное", "Формат"])
    for f in entity.fields:
        fmt = "; ".join(c for c, _ in f.options) if f.options else f.unit
        info.append([_safe(f.name), _safe(f.title), _KIND_RU[f.kind],
                     "да" if f.required else "нет", _safe(fmt)])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cell(f: FieldDef, value: Any, row: int, errors: list[dict[str, Any]]) -> str | None:
    """Katakni kanonik satrga o'giradi; bo'sh -> None."""
    bad = {"row": row, "field": f.name, "code": "invalid_value"}
    if value is None:
        return None
    if isinstance(value, bool):
        errors.append(bad)
        return None
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float | int | Decimal):
        try:  # float -> kanonik o'nlik satr (1e-05 ham)
            value = format(Decimal(repr(value)), "f")
        except InvalidOperation:
            errors.append(bad)
            return None
        if f.kind not in _NUMERIC and value.endswith(".0"):
            value = value[:-2]
    text = str(value).strip()
    if text == "":
        return None
    if f.kind in _NUMERIC:
        try:
            return _number(text, "")
        except FileFormatError:
            errors.append(bad)
            return None
    return text


def _build(entity: ManualEntity, header: list[Any], rows: Rows) -> list[dict[str, str]]:
    order = [str(h or "").strip() for h in header]
    if sorted(order) != sorted(f.name for f in entity.fields):
        raise _invalid([{"row": 1, "field": "", "code": "bad_header"}])
    by_name = {f.name: f for f in entity.fields}
    if len(rows) > MAX_ROWS:
        raise _invalid([{"row": rows[MAX_ROWS][0], "field": "", "code": "too_many_rows"}])
    if not rows:
        raise _invalid([{"row": 2, "field": "", "code": "required"}])
    items: list[dict[str, str]] = []
    errors: list[dict[str, Any]] = []
    for line, raw in rows:
        if len(raw) != len(order):
            errors.append({"row": line, "field": "", "code": "invalid_value"})
            continue
        item: dict[str, str] = {}
        for name, value in zip(order, raw, strict=True):
            v = _cell(by_name[name], value, line, errors)
            if v is not None:
                item[name] = v
        items.append(item)
    if errors:
        raise _invalid(errors)
    return items


def _nonblank(rows: Iterable[tuple[int, list[Any]]]) -> Rows:
    return [(i, r) for i, r in rows if any(c is not None and str(c).strip() for c in r)]


def _parse_csv(entity: ManualEntity, body: bytes) -> list[dict[str, str]]:
    try:
        text = body.decode("utf-8-sig")
        lines = _nonblank(enumerate(csv.reader(io.StringIO(text), delimiter=";"), start=1))
    except (UnicodeDecodeError, csv.Error):
        raise _unsupported() from None
    if not lines:
        raise _invalid([{"row": 1, "field": "", "code": "bad_header"}])
    return _build(entity, lines[0][1], lines[1:])


def _check_zip(body: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            infos = zf.infolist()
    except zipfile.BadZipFile:
        raise _unsupported() from None
    if (len(infos) > ZIP_MAX_MEMBERS or sum(i.file_size for i in infos) > ZIP_MAX_BYTES
            or any(i.filename.startswith(_BAD_ZIP) for i in infos)):
        raise _unsupported()


def _xlsx_grid(body: bytes, width: int) -> list[list[Any]]:
    """1-varaq qatorlari. Formula keshsiz katak (`data_only=True` -> None) `data_only=False`
    varaq bilan qatorma-qator solishtirib topiladi (read-only rejimda boshqa yo'li yo'q)."""
    from openpyxl import load_workbook

    wb_v = load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    wb_f = load_workbook(io.BytesIO(body), read_only=True, data_only=False)
    try:
        out: list[list[Any]] = []
        for rv, rf in zip(wb_v.worksheets[0].iter_rows(max_col=width + 1),
                          wb_f.worksheets[0].iter_rows(max_col=width + 1), strict=False):
            if any(getattr(cf, "data_type", None) == "f" and cv.value is None
                   for cv, cf in zip(rv, rf, strict=False)):
                raise _invalid([{"row": len(out) + 1, "field": "", "code": "formula_no_value"}])
            out.append([c.value for c in rv])
            if len(out) > MAX_ROWS + 1000:  # bo'sh dum qatorlari uchun zaxira
                break
        return out
    finally:
        wb_v.close()
        wb_f.close()


def _parse_xlsx(entity: ManualEntity, body: bytes) -> list[dict[str, str]]:
    _check_zip(body)
    width = len(entity.fields)
    try:
        grid = _xlsx_grid(body, width)
    except ValidationFailed:
        raise
    except Exception:  # buzuq/zararli XML (entity kengayishi ham); sabab oshkor emas
        raise _unsupported() from None
    if not grid:
        raise _invalid([{"row": 1, "field": "", "code": "bad_header"}])
    header = [*grid[0]]
    while header and header[-1] is None:
        header.pop()
    rows = _nonblank((i, [*r, *([None] * (width + 1 - len(r)))])
                     for i, r in enumerate(grid[1:], start=2))
    if len(header) == width and any(r[width] is not None for _, r in rows):
        raise _invalid([{"row": i, "field": "", "code": "invalid_value"}
                        for i, r in rows if r[width] is not None])
    return _build(entity, header, [(i, r[:width]) for i, r in rows])


def parse_upload(entity: ManualEntity, body: bytes, content_type: str) -> list[dict[str, str]]:
    if content_type == CSV_TYPE:
        return _parse_csv(entity, body)
    if content_type == XLSX_TYPE:
        return _parse_xlsx(entity, body)
    raise _unsupported()
