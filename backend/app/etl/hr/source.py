"""Kadrlar manbalari (S4 spec 3.3): HrSource protokoli — HR API (hr-api.uzgidro.uz) va
mehnat.uz (TZ 8: 3-bosqich — faqat interfeys, «не настроен»)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.core.config import ConfigError
from app.etl.hr.client import HrApiClient
from app.etl.hr.models import BreakdownRow, parse_breakdown, parse_main
from app.etl.types import ConnectorUnavailableError, HealthResult

MAIN_PATH = "/dashboard/main"
MEHNAT_MESSAGE = "mehnat.uz не подключён: интеграция предусмотрена этапом 3 ТЗ (раздел 8)"


@dataclass(frozen=True, slots=True)
class HrSnapshot:
    as_of: date
    rows: tuple[BreakdownRow, ...]
    total: int | None


class HrSource(Protocol):
    name: str

    def healthcheck(self) -> HealthResult: ...

    def snapshot(self, today: date) -> HrSnapshot: ...


class HrApiSource:
    name = "hr_api"

    def __init__(self, client: HrApiClient, breakdown_path: str) -> None:
        self.client = client
        self.breakdown_path = breakdown_path

    def healthcheck(self) -> HealthResult:
        try:
            self.client.get(MAIN_PATH)
        except ConnectorUnavailableError as exc:
            return HealthResult(False, str(exc))
        return HealthResult(True, "HR API доступен")

    def snapshot(self, today: date) -> HrSnapshot:
        total = parse_main(self.client.get(MAIN_PATH))
        rows = parse_breakdown(self.client.get(self.breakdown_path))
        return HrSnapshot(today, tuple(rows), total)


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
