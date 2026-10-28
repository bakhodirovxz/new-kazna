"""«Явка» (Кадры → Сводка) - faqat pub.attendance_daily va pub.branches (RLS + filial doirasi).

Kun - `today` dan kechmagan eng oxirgi ma'lumotli kun (bugungi yuklama hali kelmagan bo'lsa
kechagi ko'rsatiladi, `stale` belgisi bilan). «На работе» = kind attendance (keldi + kech qoldi);
«отсутствуют» = kind absence (sababsiz); sabablar - kind reason (komandirovka, kasallik, ta'til,
qolganlari «прочие»); dam olish kuni va ishdan ozod qilinganlar - «rest». Faqat agregatlar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.sections.scope import BranchSel

TRIP, SICK, LEAVE, LATE = "business_trip", "sick_leave", "annual_leave", "late"


@dataclass(slots=True)
class Figures:
    employees: int = 0
    on_work: int = 0
    late: int = 0
    absent: int = 0
    trip: int = 0
    sick: int = 0
    leave: int = 0
    other_reason: int = 0
    rest: int = 0

    def add(self, code: str, kind: str, n: int) -> None:
        if kind == "attendance":
            self.on_work += n
        if code == LATE:
            self.late += n
        if kind == "absence":
            self.absent += n
        elif kind in ("rest", "dismissed"):
            self.rest += n
        elif kind == "reason":
            if code == TRIP:
                self.trip += n
            elif code == SICK:
                self.sick += n
            elif code == LEAVE:
                self.leave += n
            else:
                self.other_reason += n


@dataclass(frozen=True, slots=True)
class StatusCount:
    code: str
    label: str
    kind: str
    employees: int


@dataclass(frozen=True, slots=True)
class BranchFigures:
    branch_id: int
    name: str
    figures: Figures


@dataclass(slots=True)
class Yavka:
    day: date | None = None
    generated_at: datetime | None = None
    stale: bool = False
    totals: Figures = field(default_factory=Figures)
    statuses: list[StatusCount] = field(default_factory=list)
    branches: list[BranchFigures] = field(default_factory=list)

    @property
    def has_source(self) -> bool:
        return self.day is not None


def load(db: Session, sel: BranchSel, *, today: date, now: datetime,
         stale_minutes: int) -> Yavka:
    where, params = sel.rows("a.branch_id")
    day = db.execute(text(f"SELECT max(a.att_date) FROM pub.attendance_daily a WHERE {where} "
                          "AND a.att_date <= :today"), {**params, "today": today}).scalar_one()
    if day is None:
        return Yavka()
    rows = db.execute(text(
        "SELECT a.branch_id, b.name, a.status_code, a.status_label, a.status_kind, a.employees, "
        "a.branch_employees, a.generated_at FROM pub.attendance_daily a "
        f"JOIN pub.branches b ON b.branch_id = a.branch_id WHERE {where} AND a.att_date = :d"),
        {**params, "d": day}).all()
    out = Yavka(day=day, generated_at=max(r.generated_at for r in rows))
    out.stale = now - out.generated_at > timedelta(minutes=stale_minutes) or day < today
    per: dict[int, BranchFigures] = {}
    counts: dict[str, StatusCount] = {}
    for r in rows:
        branch = per.setdefault(int(r.branch_id), BranchFigures(
            int(r.branch_id), r.name, Figures(employees=int(r.branch_employees))))
        branch.figures.add(r.status_code, r.status_kind, int(r.employees))
        out.totals.add(r.status_code, r.status_kind, int(r.employees))
        prev = counts.get(r.status_code)
        counts[r.status_code] = StatusCount(r.status_code, r.status_label, r.status_kind,
                                            int(r.employees) + (prev.employees if prev else 0))
    out.totals.employees = sum(b.figures.employees for b in per.values())
    out.statuses = sorted((s for s in counts.values() if s.employees > 0),
                          key=lambda s: (-s.employees, s.code))
    out.branches = sorted(per.values(), key=lambda b: (-b.figures.employees, b.name))
    return out
