"""«Кадры» API javoblari (`Hr`/`Kadry` prefiksi). Faqat agregatlar: odamlar soni, mln so'm,
soatlar, ulushlar 0..1 — ФИО yoki shaxsga oid kalit yo'q
(TZ 9, test_no_personal_fields_anywhere)."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime

from app.sections.queries.attendance import Yavka
from app.sections.queries.hr import HIDDEN_REASON, HrBranch, HrFigures, HrMonth, NamedValue
from app.sections.schemas import ReportPeriodOut, _Out


class HrKpisOut(_Out):
    has_data: bool
    snap_month: int | None
    plan: float
    fact: float
    vacancies: float | None
    vacancy_share: float | None
    fill: float | None
    payroll: float | None
    outflow: float
    payroll_share: float | None
    avg_salary: float | None
    hired: int | None
    fired: int | None
    turnover: float | None
    overtime: float | None
    overtime_per_employee: float | None
    suppressed: bool = False
    suppressed_reason: str | None = None


class HrMonthOut(_Out):
    month_id: int
    payroll: float | None
    fact: float
    avg_salary: float | None
    hired: int | None
    fired: int | None
    overtime: float | None
    suppressed: bool = False
    suppressed_reason: str | None = None


class HrCategoryOut(_Out):
    name: str
    value: float | None
    suppressed: bool = False
    suppressed_reason: str | None = None


class HrBranchOut(_Out):
    branch_id: int
    name: str
    plan: float
    fact: float
    vacancies: float | None
    fill: float | None
    payroll: float | None
    avg_salary: float | None
    hired: int | None
    fired: int | None
    turnover: float | None
    overtime: float | None
    overtime_per_employee: float | None
    suppressed: bool = False
    suppressed_reason: str | None = None


class KadrySvodOut(_Out):
    period: ReportPeriodOut
    kpis: HrKpisOut
    months: list[HrMonthOut]
    categories: list[HrCategoryOut]
    branches: list[HrBranchOut]


class KadryChislennostOut(_Out):
    period: ReportPeriodOut
    kpis: HrKpisOut
    branches: list[HrBranchOut]
    categories: list[HrCategoryOut]


class KadryFotOut(_Out):
    period: ReportPeriodOut
    kpis: HrKpisOut
    months: list[HrMonthOut]
    branches: list[HrBranchOut]


class KadryDvizhenieOut(_Out):
    period: ReportPeriodOut
    kpis: HrKpisOut
    months: list[HrMonthOut]
    branches: list[HrBranchOut]


def _reason(hidden: bool) -> str | None:
    return HIDDEN_REASON if hidden else None


def hr_kpis_out(t: HrFigures) -> HrKpisOut:
    hide = t.suppressed
    return HrKpisOut(
        has_data=t.has_data, snap_month=t.snap_month, plan=t.plan, fact=t.fact,
        vacancies=t.vacancies, vacancy_share=t.vacancy_share, fill=t.fill,
        payroll=None if hide else t.payroll, outflow=t.outflow, payroll_share=t.payroll_share,
        avg_salary=t.avg_salary, hired=None if hide else t.hired, fired=None if hide else t.fired,
        turnover=t.turnover, overtime=None if hide else t.overtime,
        overtime_per_employee=t.overtime_per_employee, suppressed=hide,
        suppressed_reason=_reason(hide and t.has_data))


def hr_branch_out(b: HrBranch) -> HrBranchOut:
    hide = b.suppressed
    return HrBranchOut(
        branch_id=b.branch_id, name=b.name, plan=b.plan, fact=b.fact, vacancies=b.vacancies,
        fill=b.fill, payroll=None if hide else b.payroll, avg_salary=b.avg_salary,
        hired=None if hide else b.hired, fired=None if hide else b.fired, turnover=b.turnover,
        overtime=None if hide else b.overtime, overtime_per_employee=b.overtime_per_employee,
        suppressed=hide, suppressed_reason=_reason(hide))


def hr_month_out(m: HrMonth) -> HrMonthOut:
    hide = m.hidden
    return HrMonthOut(
        month_id=m.month_id, payroll=None if hide else m.payroll, fact=m.fact,
        avg_salary=m.avg_salary, hired=None if hide else m.hired, fired=None if hide else m.fired,
        overtime=None if hide else m.overtime, suppressed=hide and m.fact > 0,
        suppressed_reason=_reason(hide and m.fact > 0))


def hr_category_out(c: NamedValue) -> HrCategoryOut:
    return HrCategoryOut(name=c.name, value=None if c.hidden else c.value, suppressed=c.hidden,
                         suppressed_reason=_reason(c.hidden))


class YavkaFiguresOut(_Out):
    employees: int
    on_work: int
    late: int
    absent: int
    trip: int
    sick: int
    leave: int
    other_reason: int
    rest: int


class YavkaStatusOut(_Out):
    code: str
    label: str
    kind: str
    employees: int


class YavkaBranchOut(_Out):
    branch_id: int
    name: str
    employees: int
    on_work: int
    late: int
    absent: int
    attendance_rate: float | None


class KadryYavkaOut(_Out):
    has_source: bool
    date: date | None
    generated_at: datetime | None
    stale: bool
    totals: YavkaFiguresOut
    statuses: list[YavkaStatusOut]
    branches: list[YavkaBranchOut]


def yavka_out(y: Yavka) -> KadryYavkaOut:
    return KadryYavkaOut(
        has_source=y.has_source, date=y.day, generated_at=y.generated_at, stale=y.stale,
        totals=YavkaFiguresOut(**asdict(y.totals)),
        statuses=[YavkaStatusOut(code=s.code, label=s.label, kind=s.kind, employees=s.employees)
                  for s in y.statuses],
        branches=[YavkaBranchOut(
            branch_id=b.branch_id, name=b.name, employees=b.figures.employees,
            on_work=b.figures.on_work, late=b.figures.late, absent=b.figures.absent,
            attendance_rate=(round(b.figures.on_work / b.figures.employees, 4)
                             if b.figures.employees else None)) for b in y.branches])
