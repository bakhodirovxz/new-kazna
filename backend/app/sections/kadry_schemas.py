"""«Кадры» API javoblari (`Hr`/`Kadry` prefiksi). Faqat agregatlar: odamlar soni, mln so'm,
soatlar, ulushlar 0..1 — ФИО yoki shaxsga oid kalit yo'q
(TZ 9, test_no_personal_fields_anywhere)."""

from __future__ import annotations

from app.sections.queries.hr import HrBranch, HrFigures
from app.sections.schemas import ReportPeriodOut, _Out


class HrKpisOut(_Out):
    has_data: bool
    snap_month: int | None
    plan: float
    fact: float
    vacancies: float | None
    vacancy_share: float | None
    fill: float | None
    payroll: float
    outflow: float
    payroll_share: float | None
    avg_salary: float | None
    hired: int
    fired: int
    turnover: float | None
    overtime: float
    overtime_per_employee: float | None


class HrMonthOut(_Out):
    month_id: int
    payroll: float
    fact: float
    avg_salary: float | None
    hired: int
    fired: int
    overtime: float


class HrCategoryOut(_Out):
    name: str
    value: float


class HrBranchOut(_Out):
    branch_id: int
    name: str
    plan: float
    fact: float
    vacancies: float | None
    fill: float | None
    payroll: float
    avg_salary: float | None
    hired: int
    fired: int
    turnover: float | None
    overtime: float
    overtime_per_employee: float | None


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


def hr_kpis_out(t: HrFigures) -> HrKpisOut:
    return HrKpisOut(
        has_data=t.has_data, snap_month=t.snap_month, plan=t.plan, fact=t.fact,
        vacancies=t.vacancies, vacancy_share=t.vacancy_share, fill=t.fill, payroll=t.payroll,
        outflow=t.outflow, payroll_share=t.payroll_share, avg_salary=t.avg_salary,
        hired=t.hired, fired=t.fired, turnover=t.turnover, overtime=t.overtime,
        overtime_per_employee=t.overtime_per_employee)


def hr_branch_out(b: HrBranch) -> HrBranchOut:
    return HrBranchOut(
        branch_id=b.branch_id, name=b.name, plan=b.plan, fact=b.fact, vacancies=b.vacancies,
        fill=b.fill, payroll=b.payroll, avg_salary=b.avg_salary, hired=b.hired, fired=b.fired,
        turnover=b.turnover, overtime=b.overtime, overtime_per_employee=b.overtime_per_employee)
