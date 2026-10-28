"""HrConnector — SourceConnector (S4 spec 3.3): HrSource snapshot'i (`/directory/structure`) →
fact_hr (filial × toifa × joriy oy) va dim_position (toifa).

HR filiali → bizning filial: `hr.orgs` (avval `hr_id`, keyin normallashtirilgan nom).
Moslashtirilmagan HR tashkilotlari (sho'ba korxonalar) o'tkazib yuboriladi — bitta
`unmapped_org` ogohlantirishi (soni va id'lari). Reja (штат), qabul/bo'shatish va ish vaqtidan
tashqari soatlar bu manbada yo'q — nol (ФОТ pul oqimidan).
Shaxsiy ma'lumot modelga kirmaydi (models.py).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.dwh.dates import date_id, month_id, today_tashkent
from app.etl.hr.registry import HrOrg
from app.etl.hr.source import HrSource
from app.etl.keys import normalize_name, stable_code
from app.etl.types import (
    ControlTotals,
    ExtractStats,
    HealthResult,
    ReportingSink,
    StagingSink,
    Watermark,
    Window,
)

SOURCE = "hr"
DOC_TYPE = "hr_snapshot"
ERROR_TARGET = "hr_api"


def position_code(category: str) -> str:
    return stable_code("HR-P-", normalize_name(category))


class HrConnector:
    def __init__(self, source: HrSource, orgs: Sequence[HrOrg], *, source_name: str = SOURCE,
                 today: Callable[[], date] = today_tashkent,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.source = source_name
        self.hr = source
        self.orgs = list(orgs)
        self.today = today
        self.now = now

    def healthcheck(self) -> HealthResult:
        return self.hr.healthcheck()

    def watermark(self) -> Watermark:
        return Watermark(self.now())

    def control_totals(self, window: Window) -> ControlTotals | None:
        return None

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        if not isinstance(sink, ReportingSink):
            raise TypeError("HrConnector xatolarni yozish uchun ReportingSink talab qiladi")
        snap = self.hr.snapshot(self.today())
        by_id = {o.hr_id: o.branch_code for o in self.orgs if o.hr_id is not None}
        by_name = {normalize_name(o.org): o.branch_code for o in self.orgs if o.hr_id is None}
        sums: dict[tuple[str, str], int] = defaultdict(int)
        categories: dict[str, str] = {}
        unmapped: set[int] = set()
        loaded = 0
        for row in snap.rows:
            branch = by_id.get(row.hr_id) or by_name.get(normalize_name(row.organization))
            if branch is None:
                unmapped.add(row.hr_id)
                continue
            pos = position_code(row.category)
            categories.setdefault(pos, row.category)
            sums[(branch, pos)] += row.employees
            loaded += row.employees
        if unmapped:
            ids = ", ".join(str(i) for i in sorted(unmapped)[:30])
            sink.error(target=ERROR_TARGET, code="unmapped_org", severity="warning",
                       message=f"{len(unmapped)} орг. HR пропущено (нет в hr.orgs): id {ids}")
        for pos, category in categories.items():
            sink.add("dim_position", {"code": pos, "category": category, "department": "—"})
        ym = month_id(snap.as_of)
        for (branch, pos), n in sorted(sums.items()):
            sink.add("fact_hr", self._fact(branch, pos, ym, snap.as_of, n))
        return ExtractStats(len(sums), {})

    @staticmethod
    def _fact(branch: str, pos: str, ym: int, day: date, fact: int) -> dict[str, Any]:
        return {"doc_type": DOC_TYPE, "src_id": f"{branch}:{pos}:{ym}", "date_id": date_id(day),
                "branch_code": branch, "pos_code": pos, "headcount_plan": Decimal(0),
                "headcount_fact": Decimal(fact), "payroll": Decimal(0), "hired": 0,
                "fired": 0, "overtime_hours": Decimal(0)}
