"""Konnektor protokoli va ETL qiymat tiplari (spec 5.2)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from app.dwh.dates import add_months, date_id, month_id, month_start


class Mode(StrEnum):
    FULL = "full"
    INCREMENTAL = "incremental"


class ConnectorUnavailableError(Exception):
    """Manba vaqtincha ishlamayapti — qayta urinish mumkin."""


@dataclass(frozen=True, slots=True)
class Window:
    date_from: date
    date_to: date

    @property
    def from_id(self) -> int:
        return date_id(self.date_from)

    @property
    def to_id(self) -> int:
        return date_id(self.date_to)

    def contains(self, d: date) -> bool:
        return self.date_from <= d <= self.date_to

    def contains_id(self, value: int) -> bool:
        return self.from_id <= value <= self.to_id

    def month_ids(self) -> list[int]:
        out: list[int] = []
        cur = month_start(self.date_from)
        while cur <= self.date_to:
            out.append(month_id(cur))
            cur = add_months(cur, 1)
        return out


@dataclass(frozen=True, slots=True)
class Watermark:
    value: datetime | None


@dataclass(frozen=True, slots=True)
class HealthResult:
    ok: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ExtractStats:
    rows: int
    by_target: Mapping[str, int]  # to'liq berilgan maqsadlar (0 qatorlilari ham)


@dataclass(frozen=True, slots=True)
class ControlTotals:
    cashflow_by_month: Mapping[int, Decimal]  # month_id → 5110/5210/5530 oborotlari


class StagingSink(Protocol):
    def add(self, target: str, row: Mapping[str, Any]) -> None: ...


@runtime_checkable
class ReportingSink(StagingSink, Protocol):
    """Qator/fayl xatolarini core.etl_error ga yoza oladigan sink (bank fayllari — S2 spec 3.2)."""

    load_id: int

    def error(self, *, target: str, code: str, message: str, src_id: str | None = None,
              severity: str = "error") -> None: ...


class SourceConnector(Protocol):
    source: str

    def healthcheck(self) -> HealthResult: ...

    def watermark(self) -> Watermark: ...

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats: ...

    def control_totals(self, window: Window) -> ControlTotals | None: ...
