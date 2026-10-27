"""«Инвестиции» API javoblari (`Inv` prefiksi). Pul — mln so'm, ulushlar 0..1, uzilish —
foiz punktlari; status: ok | lag | risk | None."""

from __future__ import annotations

from datetime import date

from app.sections.queries.investment import InvObject, InvTotals
from app.sections.schemas import ReportPeriodOut, _Out


class InvKpisOut(_Out):
    has_objects: bool
    objects: int
    total_cost: float
    program: float
    plan_to_date: float
    fact_ytd: float
    execution: float | None
    fact_period: float
    lagging: int
    threatened: int
    commissioning: int
    year: int


class InvObjectOut(_Out):
    object_id: int
    object_code: str
    name: str
    program_code: str | None
    work_type: str
    source_name: str
    commissioning_year: int | None
    total_cost: float | None
    branch_id: int
    branch_name: str
    plan_year: float
    plan_to_date: float
    fact_ytd: float
    fact_period: float
    execution: float | None
    status: str | None
    financial: float | None
    physical: float | None
    gap_pp: float | None
    advance: float
    advance_days: int | None


class InvCumOut(_Out):
    month_id: int
    plan: float
    fact: float | None


class InvSourceOut(_Out):
    name: str
    plan_year: float
    fact_ytd: float
    share: float | None


class InvStageOut(_Out):
    stage_no: int
    name: str
    plan_date: date
    fact_date: date | None
    done: bool
    late: bool


class InvObjectStagesOut(_Out):
    object_id: int
    name: str
    branch_id: int
    late: int
    stages: list[InvStageOut]


class InvSvodOut(_Out):
    period: ReportPeriodOut
    kpis: InvKpisOut
    cumulative: list[InvCumOut]
    sources: list[InvSourceOut]
    objects: list[InvObjectOut]


class InvObektyOut(_Out):
    period: ReportPeriodOut
    kpis: InvKpisOut
    objects: list[InvObjectOut]


class InvIstochnikiOut(_Out):
    period: ReportPeriodOut
    kpis: InvKpisOut
    sources: list[InvSourceOut]
    objects: list[InvObjectOut]
    cumulative: list[InvCumOut]


class InvRiskiOut(_Out):
    period: ReportPeriodOut
    kpis: InvKpisOut
    lagging: list[InvObjectOut]
    gaps: list[InvObjectOut]
    stages: list[InvObjectStagesOut]
    advances: list[InvObjectOut]


def inv_kpis_out(t: InvTotals) -> InvKpisOut:
    return InvKpisOut(
        has_objects=t.has_objects, objects=len(t.objects), total_cost=t.total_cost,
        program=t.program, plan_to_date=t.plan_to_date, fact_ytd=t.fact_ytd,
        execution=t.execution, fact_period=t.fact_period, lagging=t.lagging,
        threatened=t.threatened, commissioning=t.commissioning, year=t.year)


def object_out(o: InvObject) -> InvObjectOut:
    return InvObjectOut(
        object_id=o.object_id, object_code=o.object_code, name=o.name,
        program_code=o.program_code, work_type=o.work_type, source_name=o.source_name,
        commissioning_year=o.commissioning_year, total_cost=o.total_cost, branch_id=o.branch_id,
        branch_name=o.branch_name, plan_year=o.plan_year, plan_to_date=o.plan_to_date,
        fact_ytd=o.fact_ytd, fact_period=o.fact_period, execution=o.execution, status=o.status,
        financial=o.financial, physical=o.physical, gap_pp=o.gap_pp, advance=o.advance,
        advance_days=o.advance_days)
