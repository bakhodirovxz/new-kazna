"""CbuRatesConnector — SourceConnector (S2 spec 3.3): so'ralgan har kalendar kun uchun shu kuni
amalda bo'lgan kurs dwh.fx_rate ga (currency, date_id) kaliti bilan — idempotent.
Kuniga oxirgi `days` kun (o'tkazib yuborilganlar to'ldiriladi); tarix — date_from/date_to.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta

from app.core.logging import get_logger
from app.dwh.dates import date_id, today_tashkent
from app.etl.cbu.client import CbuClient, CbuError
from app.etl.types import (
    ConnectorUnavailableError,
    ControlTotals,
    ExtractStats,
    HealthResult,
    StagingSink,
    Watermark,
    Window,
)

SOURCE = "cbu"
MAX_BACKFILL_DAYS = 800
log = get_logger("ugekazna.cbu")


class CbuRatesConnector:
    buffered = True  # runner HTTP davomida DB tranzaksiyasini ochmaydi (M9)

    def __init__(self, client: CbuClient, currencies: Sequence[str], *, days: int = 7,
                 date_from: date | None = None, date_to: date | None = None,
                 today: Callable[[], date] = today_tashkent,
                 sleep: Callable[[float], None] = time.sleep, pause: float = 0.2,
                 source: str = SOURCE) -> None:
        if (date_from is None) != (date_to is None):
            raise ValueError("date_from va date_to birga beriladi")
        if date_from is not None and date_to is not None:
            if date_to < date_from:
                raise ValueError("date_to date_from dan oldin")
            if (date_to - date_from).days + 1 > MAX_BACKFILL_DAYS:
                raise ValueError(f"bir martada ko'pi bilan {MAX_BACKFILL_DAYS} kun")
        self.source = source
        self.client = client
        self.currencies = list(currencies)
        self.days = days
        self.date_from = date_from
        self.date_to = date_to
        self.today = today
        self.sleep = sleep
        self.pause = pause

    def dates(self) -> list[date]:
        if self.date_from is not None and self.date_to is not None:
            start, end = self.date_from, self.date_to
        else:
            end = self.today()
            start = end - timedelta(days=self.days - 1)
        return [start + timedelta(days=n) for n in range((end - start).days + 1)]

    def healthcheck(self) -> HealthResult:
        try:
            self.client.rates(self.today())
        except ConnectorUnavailableError as exc:
            return HealthResult(False, str(exc))
        return HealthResult(True, "cbu.uz")

    def watermark(self) -> Watermark:
        return Watermark(datetime.now(UTC))

    def control_totals(self, window: Window) -> ControlTotals | None:
        return None

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        wanted = set(self.currencies)
        count = 0
        for n, day in enumerate(self.dates()):
            if n:
                self.sleep(self.pause)
            rates = self.client.rates(day)
            if not rates:
                log.warning("cbu_empty_response", day=day.isoformat())
                continue
            found: set[str] = set()
            for r in rates:
                if r.ccy not in wanted:
                    continue
                if r.day > day:
                    raise CbuError(f"ЦБ {day:%d.%m.%Y}: курс {r.ccy} датирован "
                                   f"{r.day:%d.%m.%Y} — позже запрошенной даты")
                sink.add("fx_rate", {"currency": r.ccy, "date_id": date_id(day),
                                     "rate": r.per_unit})
                found.add(r.ccy)
                count += 1
            if wanted - found:
                log.warning("cbu_missing_currencies", day=day.isoformat(),
                            currencies=sorted(wanted - found))
        return ExtractStats(count, {"fx_rate": count})
