"""«Закупки» API javoblari (OpenAPI komponent nomlari noyob — `Zak` prefiksi). Pul — mln so'm,
ulushlar 0..1, kunlar — butun; None — maxraj 0 yoki ma'lumot yo'q."""

from __future__ import annotations

from datetime import date

from app.dwh.dates import from_date_id
from app.sections.queries.procurement import LotRow, MethodRow, ProcFigures
from app.sections.schemas import ReportPeriodOut, _Out


class ZakKpisOut(_Out):
    has_data: bool
    contracted: float
    contracts: int
    start_contracted: float
    savings: float
    savings_share: float | None
    ytd: float
    plan: float
    plan_execution: float | None
    in_work: int
    in_work_start: float
    overdue: int
    overdue_start: float
    direct: float
    direct_share: float | None
    avg_days: float | None
    cancelled: int
    cancelled_start: float


class ZakMonthOut(_Out):
    month_id: int
    contracted: float


class ZakMethodOut(_Out):
    method: str
    title: str
    lots: int
    start: float
    contracted: float
    savings: float
    savings_share: float | None
    avg_days: float | None
    norm_days: int | None


class ZakLotOut(_Out):
    lot_no: str
    branch_id: int
    branch_name: str
    date: date
    method: str
    method_title: str
    subject: str
    status: str
    kind: str
    start_price: float
    contract_price: float | None
    days: int | None
    norm_days: int | None
    overdue: bool
    supplier: str | None


class ZakNamedOut(_Out):
    name: str
    amount: float
    count: int


class ZakBranchOut(_Out):
    branch_id: int
    name: str
    plan: float
    ytd: float
    execution: float | None
    savings: float


class ZakSvodOut(_Out):
    period: ReportPeriodOut
    kpis: ZakKpisOut
    months: list[ZakMonthOut]
    methods: list[ZakMethodOut]
    lots: list[ZakLotOut]


class ZakLotyOut(_Out):
    period: ReportPeriodOut
    kpis: ZakKpisOut
    lots: list[ZakLotOut]
    truncated: bool


class ZakPostavshikiOut(_Out):
    period: ReportPeriodOut
    kpis: ZakKpisOut
    suppliers: list[ZakNamedOut]
    subjects: list[ZakNamedOut]
    branches: list[ZakBranchOut]


class ZakEkonomiyaOut(_Out):
    period: ReportPeriodOut
    kpis: ZakKpisOut
    methods: list[ZakMethodOut]
    cancelled: list[ZakLotOut]


def zak_kpis_out(t: ProcFigures) -> ZakKpisOut:
    return ZakKpisOut(
        has_data=t.has_data, contracted=t.contracted, contracts=t.contracts,
        start_contracted=t.start_contracted, savings=t.savings, savings_share=t.savings_share,
        ytd=t.ytd, plan=t.plan, plan_execution=t.plan_execution, in_work=t.in_work,
        in_work_start=t.in_work_start, overdue=t.overdue, overdue_start=t.overdue_start,
        direct=t.direct, direct_share=t.direct_share, avg_days=t.avg_days,
        cancelled=t.cancelled, cancelled_start=t.cancelled_start)


def method_out(m: MethodRow) -> ZakMethodOut:
    return ZakMethodOut(method=m.method, title=m.title, lots=m.lots, start=m.start,
                        contracted=m.contracted, savings=m.savings,
                        savings_share=m.savings_share, avg_days=m.avg_days,
                        norm_days=m.norm_days)


def lot_out(r: LotRow) -> ZakLotOut:
    return ZakLotOut(
        lot_no=r.lot_no, branch_id=r.branch_id, branch_name=r.branch_name,
        date=from_date_id(r.date_id), method=r.method, method_title=r.method_title,
        subject=r.subject, status=r.status, kind=r.kind, start_price=r.start_price,
        contract_price=r.contract_price, days=r.days, norm_days=r.norm_days, overdue=r.overdue,
        supplier=r.supplier)
