"""FileConnector (spec 5.2, TZ 8 "Общие правила обмена"): CSV, UTF-8, ';', ISO 8601 sanalar,
summalarda razryad ajratkichi yo'q.

Katalogda har staging maqsadi uchun `<maqsad>.csv` (sarlavha — payload kalitlari: `code`,
`branch_code`, `item_code`, ...). `date` → `date_id`, `status_date` → `status_date_id`.
Ixtiyoriy `control_totals.csv` (`month;amount`) — 1C oborotlari (5110/5210/5530).
Format xatosi — FileFormatError/ValueError (qayta urinilmaydi), fayl/katalog yo'qligi —
vaqtinchalik xato.
"""

from __future__ import annotations

import csv
import os
import re
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.dwh.dates import date_id
from app.dwh.targets import TARGETS, Target
from app.etl.errors import FileFormatError
from app.etl.types import (
    ControlTotals,
    ExtractStats,
    HealthResult,
    StagingSink,
    Watermark,
    Window,
)

NUMERIC_COLUMNS = frozenset({
    "amount", "balance", "capacity_mw", "lat", "lon", "rate", "amount_uzs", "total_cost",
    "receivable", "payable", "overdue", "generation", "own_needs", "supply", "plan",
    "work_hours", "accrued", "paid", "volume", "start_price", "contract_price", "qty", "value",
    "min_qty", "fact", "physical_pct", "advance", "principal", "interest", "headcount_plan",
    "headcount_fact", "payroll", "overtime_hours", "allocated", "used",
})
_THOUSANDS = re.compile(r"^-?\d{1,3}([ \u00a0\u2009\u202f']\d{3})+([.,]\d+)?$")
_DECIMAL_COMMA = re.compile(r"^-?\d+,\d+$")


def _number(value: str, where: str) -> str:
    if _THOUSANDS.match(value):
        raise FileFormatError(f"{where}: разделитель разрядов в числе не допускается")
    if _DECIMAL_COMMA.match(value):
        value = value.replace(",", ".")
    try:
        Decimal(value)
    except InvalidOperation as exc:
        raise FileFormatError(f"{where}: неверное число") from exc
    return value


def _iso_date(value: str, where: str) -> int:
    try:
        return date_id(date.fromisoformat(value))
    except ValueError as exc:
        raise FileFormatError(f"{where}: неверная дата (ожидается ГГГГ-ММ-ДД)") from exc


class FileConnector:
    def __init__(self, directory: Path, *, source: str = "file") -> None:
        self.directory = directory
        self.source = source

    def healthcheck(self) -> HealthResult:
        if not self.directory.is_dir():
            return HealthResult(False, f"каталог не найден: {self.directory}")
        if not os.access(self.directory, os.R_OK):
            return HealthResult(False, f"нет доступа к каталогу: {self.directory}")
        return HealthResult(True, str(self.directory))

    def watermark(self) -> Watermark:
        files = list(self.directory.glob("*.csv")) if self.directory.is_dir() else []
        if not files:
            return Watermark(None)
        return Watermark(datetime.fromtimestamp(max(f.stat().st_mtime for f in files), tz=UTC))

    def _rows(self, path: Path) -> Iterator[tuple[int, dict[str, str]]]:
        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=";")
                for line, raw in enumerate(reader, start=2):
                    if None in raw:
                        raise FileFormatError(f"{path.name}:{line}: лишние поля в строке")
                    yield line, {k.strip(): (v or "").strip() for k, v in raw.items()}
        except UnicodeDecodeError as exc:
            raise FileFormatError(f"{path.name}: файл не в кодировке UTF-8") from exc

    def _convert(self, target: Target, raw: dict[str, str], where: str) -> dict[str, Any]:
        row: dict[str, Any] = {}
        for key, value in raw.items():
            is_date = key == "date" or key.endswith("_date")
            out_key = f"{key}_id" if is_date and f"{key}_id" in target.columns else key
            if value == "":
                row[out_key] = None
            elif out_key != key:
                row[out_key] = _iso_date(value, where)
            elif key in NUMERIC_COLUMNS:
                row[key] = _number(value, where)
            else:
                row[key] = value
        return row

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        counts: dict[str, int] = {}
        for name, target in TARGETS.items():
            path = self.directory / f"{name}.csv"
            if not path.is_file():
                continue
            counts[name] = 0
            for line, raw in self._rows(path):
                row = self._convert(target, raw, f"{path.name}:{line}")
                if target.kind == "fact" and row.get("date_id") is not None \
                        and not window.contains_id(int(row["date_id"])):
                    continue
                sink.add(name, row)
                counts[name] += 1
        return ExtractStats(sum(counts.values()), counts)

    def control_totals(self, window: Window) -> ControlTotals | None:
        path = self.directory / "control_totals.csv"
        if not path.is_file():
            return None
        months = set(window.month_ids())
        totals: dict[int, Decimal] = {}
        for line, raw in self._rows(path):
            month = int(raw["month"])
            if month in months:
                totals[month] = Decimal(_number(raw["amount"], f"{path.name}:{line}"))
        return ControlTotals(totals)
