"""HrConnector — SourceConnector (S4 spec 3.3): HrSource snapshot'i → fact_hr (filial × toifa ×
joriy oy) va dim_position (toifa).

Tashkilot → filial `hr.orgs` (normallashtirilgan nom). Tashkilot kesimi umuman yo'q —
`no_branch_breakdown` ogohlantirishi, fact_hr yozilmaydi (spec 11.6). Moslashtirilmagan
tashkilot — `unmapped_org` (xato, qatorlari o'tkaziladi). Yuklangan jami `/dashboard/main`
jamidan 1% dan ko'p farq qilsa — `total_mismatch` ogohlantirishi. Upsert: oy ichida kalit bir
xil (sana — bugun, oxirgi snapshot qoladi). Shaxsiy ma'lumot modelga kirmaydi (models.py).
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
TOTAL_TOLERANCE = 0.01


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
        if not any(r.organization for r in snap.rows):
            sink.error(target=ERROR_TARGET, code="no_branch_breakdown", severity="warning",
                       message="HR API не даёт разреза по организациям — численность филиалов "
                               "не загружена (docs/integration/hr-sorov-s4.md)")
            return ExtractStats(0, {})
        by_org = {normalize_name(o.org): o.branch_code for o in self.orgs}
        sums: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(
            lambda: defaultdict(Decimal))
        categories: dict[str, str] = {}
        unmapped: set[str] = set()
        loaded = 0
        for row in snap.rows:
            if row.organization is None:
                unmapped.add("")
                continue
            branch = by_org.get(normalize_name(row.organization))
            if branch is None:
                unmapped.add(row.organization)
                continue
            pos = position_code(row.category)
            categories.setdefault(pos, row.category)
            acc = sums[(branch, pos)]
            acc["plan"] += row.staff or Decimal(0)
            acc["fact"] += Decimal(row.employees)
            acc["hired"] += Decimal(row.hired or 0)
            acc["fired"] += Decimal(row.fired or 0)
            acc["overtime"] += row.overtime or Decimal(0)
            loaded += row.employees
        for org in sorted(unmapped):
            if org:
                sink.error(target=ERROR_TARGET, code="unmapped_org",
                           message=f"организация «{org[:80]}» не сопоставлена с филиалом "
                                   "(hr.orgs)")
            else:
                sink.error(target=ERROR_TARGET, code="no_org",
                           message="строки без организации пропущены")
        for pos, category in categories.items():
            sink.add("dim_position", {"code": pos, "category": category, "department": "—"})
        ym = month_id(snap.as_of)
        for (branch, pos), acc in sorted(sums.items()):
            sink.add("fact_hr", self._fact(branch, pos, ym, snap.as_of, acc))
        if snap.total and abs(loaded - snap.total) > snap.total * TOTAL_TOLERANCE:
            sink.error(target=ERROR_TARGET, code="total_mismatch", severity="warning",
                       message=f"сумма по филиалам {loaded} не совпадает с общей численностью "
                               f"{snap.total}")
        return ExtractStats(len(sums), {})

    @staticmethod
    def _fact(branch: str, pos: str, ym: int, day: date,
              acc: dict[str, Decimal]) -> dict[str, Any]:
        return {"doc_type": DOC_TYPE, "src_id": f"{branch}:{pos}:{ym}", "date_id": date_id(day),
                "branch_code": branch, "pos_code": pos, "headcount_plan": acc["plan"],
                "headcount_fact": acc["fact"], "payroll": Decimal(0), "hired": int(acc["hired"]),
                "fired": int(acc["fired"]), "overtime_hours": acc["overtime"]}
