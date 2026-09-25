"""SyntheticConnector (spec 5.2): dev/test/yuklama testi uchun deterministik manba."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal

from app.core.config import get_settings
from app.dwh.dates import TASHKENT, month_id, today_tashkent
from app.etl.synthetic.families import FAMILIES
from app.etl.synthetic.model import HISTORY_START, SynthModel
from app.etl.types import (
    ControlTotals,
    ExtractStats,
    HealthResult,
    StagingSink,
    Watermark,
    Window,
)


class SyntheticConnector:
    def __init__(self, *, seed: int | None = None, as_of: date | None = None,
                 history_start: date = HISTORY_START, source: str = "synthetic") -> None:
        self.source = source
        self.seed = get_settings().synthetic_seed if seed is None else seed
        self.as_of = as_of or today_tashkent()
        self.model = SynthModel(self.seed, self.as_of, history_start)

    def healthcheck(self) -> HealthResult:
        return HealthResult(True, "synthetic")

    def watermark(self) -> Watermark:
        return Watermark(datetime.combine(self.as_of, time(0), tzinfo=TASHKENT))

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        counts: dict[str, int] = {}
        for _name, family in FAMILIES:
            counts.update(family(self.model, window, sink))
        return ExtractStats(sum(counts.values()), counts)

    def control_totals(self, window: Window) -> ControlTotals | None:
        totals: dict[int, Decimal] = defaultdict(Decimal)
        for posting in self.model.cash.postings:
            if window.contains(posting.day):
                totals[month_id(posting.day)] += posting.amount
        return ControlTotals(dict(totals))
