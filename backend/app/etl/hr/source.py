"""Kadrlar manbalari (S4 spec 3.3): HrSource protokoli — HR API (hr-api.uzgidro.uz) va
mehnat.uz (TZ 8: 3-bosqich — faqat interfeys, «не настроен»)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.core.config import ConfigError
from app.etl.hr.client import HrApiClient
from app.etl.hr.models import (
    AttendanceReport,
    StructureRow,
    parse_attendance,
    parse_structure,
    parse_total,
)
from app.etl.types import ConnectorUnavailableError, HealthResult

STRUCTURE_PATH = "/directory/structure"
ATTENDANCE_PATH = "/directory/attendance"
MEHNAT_MESSAGE = "mehnat.uz не подключён: интеграция предусмотрена этапом 3 ТЗ (раздел 8)"


@dataclass(frozen=True, slots=True)
class HrSnapshot:
    as_of: date
    rows: tuple[StructureRow, ...]
    total: int | None


class HrSource(Protocol):
    name: str

    def healthcheck(self) -> HealthResult: ...

    def snapshot(self, today: date) -> HrSnapshot: ...


class HrApiSource:
    name = "hr_api"

    def __init__(self, client: HrApiClient) -> None:
        self.client = client

    def healthcheck(self) -> HealthResult:
        try:
            self.client.get(STRUCTURE_PATH, {"include_empty": "false"})
        except ConnectorUnavailableError as exc:
            return HealthResult(False, str(exc))
        return HealthResult(True, "HR API доступен")

    def snapshot(self, today: date) -> HrSnapshot:
        data = self.client.get(STRUCTURE_PATH, {"include_empty": "false"})
        return HrSnapshot(today, tuple(parse_structure(data)), parse_total(data))

    def attendance(self, day: date) -> AttendanceReport:
        # size=1: ro'yxat (F.I.Sh.) kerak emas; `items` parse_attendance'da o'qilmaydi
        return parse_attendance(self.client.get(ATTENDANCE_PATH, {
            "size": "1", "include_days": "false", "date": day.isoformat()}))


class MehnatNotConfigured(ConfigError):  # noqa: N818
    """mehnat.uz — TZ 8 bo'yicha 3-bosqich (spec 2, «Kirmaydi»)."""


class MehnatSource:
    name = "mehnat"

    def __init__(self) -> None:
        raise MehnatNotConfigured(MEHNAT_MESSAGE)

    def healthcheck(self) -> HealthResult:
        raise MehnatNotConfigured(MEHNAT_MESSAGE)

    def snapshot(self, today: date) -> HrSnapshot:
        raise MehnatNotConfigured(MEHNAT_MESSAGE)
