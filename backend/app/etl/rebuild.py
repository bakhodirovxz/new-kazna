"""Manbasiz qayta hisob (S5 spec 3.4): faktlar o'zgarmaydi — Runner agregatlarni (финмодель
ham), sifat tekshiruvlarini va publish'ni bajaradi. Admin «Пересчитать модель» →
`POST /admin/etl/run {"source": "rebuild", "mode": "full"}` → worker navbati."""

from __future__ import annotations

from app.etl.types import (
    ControlTotals,
    ExtractStats,
    HealthResult,
    StagingSink,
    Watermark,
    Window,
)


class RebuildConnector:
    source = "rebuild"

    def healthcheck(self) -> HealthResult:
        return HealthResult(True)

    def watermark(self) -> Watermark:
        return Watermark(None)

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        return ExtractStats(0, {})  # hech bir maqsad «to'liq» emas — hech narsa o'chirilmaydi

    def control_totals(self, window: Window) -> ControlTotals | None:
        return None
