"""Sintetik kunlik davomat (HR API /directory/attendance shakli): 16 ta demo filial, deterministik
(seed, filial, kun). Hafta oxiri - deyarli hamma dam olishda. Xodimlar soni fact_hr (штат x
to'ldirilish) bilan bir xil. F.I.Sh. yo'q. Sintetik filial `id` = `hr_id` (demo moslashtirish)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy.engine import Connection

from app.etl.hr.attendance import StoreResult, store
from app.etl.hr.models import AttendanceReport, BranchAttendance, Status
from app.etl.hr.registry import HrOrg
from app.etl.synthetic.families.hr import staff
from app.etl.synthetic.model import SynthModel
from app.etl.synthetic.reference import BRANCHES
from app.etl.synthetic.rng import rnd

STATUSES = (
    Status("present", "Kelgan", "attendance"), Status("late", "Kech qolgan", "attendance"),
    Status("absent", "Kelmagan (sababsiz)", "absence"), Status("day_off", "Dam olish kuni", "rest"),
    Status("business_trip", "Xizmat safari", "reason"),
    Status("sick_leave", "Kasallik varaqasi", "reason"),
    Status("annual_leave", "Mehnat ta'tili", "reason"), Status("otgul", "Otgul", "reason"))
# ish kuni ulushlari (qolgani - kelgan)
SHARES = (("late", 0.03, 0.08), ("absent", 0.005, 0.03), ("business_trip", 0.01, 0.05),
          ("sick_leave", 0.01, 0.03), ("annual_leave", 0.03, 0.09), ("otgul", 0.0, 0.01))
DEMO_ORGS = [HrOrg(org=b.name, branch_code=b.code, hr_id=b.id) for b in BRANCHES]


def attendance_report(model: SynthModel, day: date, generated_at: datetime) -> AttendanceReport:
    branches = []
    for branch in BRANCHES:
        _plan, total = staff(model, branch)
        r = rnd(model.seed, "attendance", branch.id, day.toordinal())
        counts = dict.fromkeys((s.code for s in STATUSES), 0)
        if day.weekday() >= 5:
            counts["day_off"] = total
        else:
            for code, lo, hi in SHARES:
                counts[code] = round(total * r.uniform(lo, hi))
            counts["present"] = max(0, total - sum(counts.values()))
        branches.append(BranchAttendance(branch.id, total, {
            code: (n, n) for code, n in counts.items()}))
    return AttendanceReport(day, generated_at.astimezone(UTC), STATUSES, tuple(branches))


def seed_attendance(conn: Connection, model: SynthModel, today: date, *, days: int = 7,
                    now: datetime | None = None) -> StoreResult:
    """Oxirgi `days` kun (bugun bilan) - demo uchun; bugungisi `now` bilan yangi hisoblanadi."""
    moment = now or datetime.now(UTC)
    stored = skipped = 0
    for back in range(days):
        day = date.fromordinal(today.toordinal() - back)
        result = store(conn, attendance_report(model, day, moment), DEMO_ORGS)
        stored, skipped = stored + result.stored, max(skipped, result.skipped_branches)
    return StoreResult(stored, skipped)
