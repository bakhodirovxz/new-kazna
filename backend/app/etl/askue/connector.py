"""AskueConnector — SourceConnector (S3 spec 3.1): AskueExport fayllari → kanonik CSV →
fact_generation (stansiya × sutka, MVt·soat ÷ 1000 = mln kVt·soat).

Stansiya kodi → filial `askue.stations` orqali; moslashtirilmagan stansiya, buzilgan qator yoki
fayl → core.etl_error (ReportingSink, step extract, target askue_file), yaroqli qatorlar yuklanadi.
Maqsadlar «to'liq» deb belgilanmaydi (upsert, kalit stansiya:sana): fayllar inkremental.
Sutkalik ishlab chiqarish > quvvat × 24 → 2-reja sifat tekshiruvi 4 publish'ni to'xtatadi.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Decimal

from app.core.logging import get_logger
from app.dwh.dates import date_id, today_tashkent
from app.etl.askue.canonical import AskueFileError, parse_canonical
from app.etl.askue.export import AskueExport
from app.etl.askue.registry import AskueStation
from app.etl.types import (
    ControlTotals,
    ExtractStats,
    HealthResult,
    ReportingSink,
    StagingSink,
    Watermark,
    Window,
)

SOURCE = "askue"
DOC_TYPE = "askue_daily"
ERROR_TARGET = "askue_file"
ERROR_LIMIT = 1000
_MWH_IN_MLN_KWH = Decimal(1000)
_VOLUME = Decimal("0.001")
log = get_logger("ugekazna.askue")


def to_mln_kwh(mwh: Decimal) -> Decimal:
    return (mwh / _MWH_IN_MLN_KWH).quantize(_VOLUME, rounding=ROUND_HALF_EVEN)


class AskueConnector:
    def __init__(self, export: AskueExport, stations: Sequence[AskueStation], *,
                 source: str = SOURCE, today: Callable[[], date] = today_tashkent,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.source = source
        self.export = export
        self.stations = list(stations)
        self.today = today
        self.now = now

    def healthcheck(self) -> HealthResult:
        return self.export.healthcheck()

    def watermark(self) -> Watermark:
        return Watermark(self.now())

    def control_totals(self, window: Window) -> ControlTotals | None:
        return None

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        if not isinstance(sink, ReportingSink):
            raise TypeError("AskueConnector xatolarni yozish uchun ReportingSink talab qiladi")
        by_code = {s.code: s for s in self.stations}
        today = self.today()
        rows = errors = skipped = 0

        def report(code: str, message: str) -> None:
            nonlocal errors
            errors += 1
            if errors <= ERROR_LIMIT:
                sink.error(target=ERROR_TARGET, code=code, message=message[:500])

        for export_file in self.export.files(window):
            name = export_file.name[:120]
            if export_file.error:
                report(export_file.error, f"{name}: файл больше допустимого размера")
                continue
            try:
                parsed = parse_canonical(export_file.data, today=today)
            except AskueFileError as exc:
                report(exc.code, f"{name}: {exc.message}")
                continue
            for err in parsed.errors:
                report(err.code, f"{name}:{err.line}: {err.message}")
            for row in parsed.rows:
                station = by_code.get(row.station)
                if station is None:
                    report("unknown_station", f"{name}:{row.line}: станция «{row.station}» не "
                                              "сопоставлена с филиалом (askue.stations)")
                    continue
                if not window.contains(row.day):
                    skipped += 1
                    continue
                generation = to_mln_kwh(row.generation)
                own = to_mln_kwh(row.own_needs)
                supply = to_mln_kwh(row.supply) if row.supply is not None else generation - own
                sink.add("fact_generation", {
                    "doc_type": DOC_TYPE, "src_id": f"{row.station}:{date_id(row.day)}",
                    "date_id": date_id(row.day), "branch_code": station.branch_code,
                    "generation": generation, "own_needs": own, "supply": supply,
                    "plan": None, "work_hours": row.work_hours})
                rows += 1
        if errors > ERROR_LIMIT:
            sink.error(target=ERROR_TARGET, code="too_many_errors",
                       message=f"ещё {errors - ERROR_LIMIT} ошибок не записано")
        if skipped:
            log.info("askue_rows_outside_window", skipped=skipped)
        return ExtractStats(rows, {})
