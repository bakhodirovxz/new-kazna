"""«Производство» API javoblari (OpenAPI komponent nomlari noyob). Ishlab chiqarish — mln kVt·soat,
pul — mln so'm, quvvat — MVt, ulushlar 0..1; None — maxraj 0 yoki ma'lumot yo'q."""

from __future__ import annotations

from datetime import datetime

from app.sections.queries.power import PowerReport
from app.sections.queries.production import GenFigures, GenMonth
from app.sections.schemas import ReportPeriodOut, StationProductionOut, _Out


class ProdKpisOut(_Out):
    has_data: bool
    generation: float
    generation_prev: float
    plan: float
    execution: float | None
    capacity_mw: float | None
    stations: int
    kium: float | None
    own_needs: float
    own_share: float | None
    supply: float
    accrued: float
    paid: float
    payment_level: float | None


class GenMonthOut(_Out):
    month_id: int
    generation: float
    plan: float
    generation_prev: float


class SalesMonthOut(_Out):
    month_id: int
    accrued: float
    paid: float


class StationGenOut(_Out):
    branch_id: int
    name: str
    short_name: str
    capacity_mw: float | None
    generation: float
    generation_prev: float
    plan: float
    execution: float | None
    kium: float | None
    supply: float
    own_share: float | None
    accrued: float
    paid: float
    payment_level: float | None


class MapStationOut(_Out):
    branch_id: int
    code: str
    name: str
    short_name: str
    kind: str
    capacity_mw: float | None
    lat: float | None
    lon: float | None
    production: StationProductionOut | None


class ProizvSvodOut(_Out):
    period: ReportPeriodOut
    has_stations: bool
    kpis: ProdKpisOut
    months: list[GenMonthOut]
    stations: list[StationGenOut]
    map: list[MapStationOut]


class ProizvStanciiOut(_Out):
    period: ReportPeriodOut
    has_stations: bool
    kpis: ProdKpisOut
    stations: list[StationGenOut]


class ProizvRealizOut(_Out):
    period: ReportPeriodOut
    has_stations: bool
    kpis: ProdKpisOut
    months: list[SalesMonthOut]
    stations: list[StationGenOut]


def kpis_out(t: GenFigures) -> ProdKpisOut:
    return ProdKpisOut(
        has_data=t.has_data, generation=t.generation, generation_prev=t.generation_prev,
        plan=t.plan, execution=t.execution, capacity_mw=t.capacity_mw, stations=t.stations,
        kium=t.kium, own_needs=t.own_needs, own_share=t.own_share, supply=t.supply,
        accrued=t.accrued, paid=t.paid, payment_level=t.payment_level)


def station_out(s: GenFigures) -> StationGenOut:
    return StationGenOut(
        branch_id=s.branch_id, name=s.name, short_name=s.short_name, capacity_mw=s.capacity_mw,
        generation=s.generation, generation_prev=s.generation_prev, plan=s.plan,
        execution=s.execution, kium=s.kium, supply=s.supply, own_share=s.own_share,
        accrued=s.accrued, paid=s.paid, payment_level=s.payment_level)


def gen_month_out(m: GenMonth) -> GenMonthOut:
    return GenMonthOut(month_id=m.month_id, generation=m.generation, plan=m.plan,
                       generation_prev=m.generation_prev)


def sales_month_out(m: GenMonth) -> SalesMonthOut:
    return SalesMonthOut(month_id=m.month_id, accrued=m.accrued, paid=m.paid)


def production_out(s: GenFigures | None) -> StationProductionOut | None:
    if s is None or not s.has_data:
        return None
    return StationProductionOut(generation=s.generation, plan=s.plan, execution=s.execution,
                                kium=s.kium, payment_level=s.payment_level)


class PowerStationOut(_Out):
    branch_id: int
    branch_name: str
    station: str
    station_name: str
    cascade_name: str
    power_mw: float
    units_working: int
    units_reserve: int
    units_repair: int


class PowerOut(_Out):
    has_source: bool
    snap_at: datetime | None
    source_date: str | None
    stale: bool
    total_mw: float
    units_working: int
    units_reserve: int
    units_repair: int
    stations: list[PowerStationOut]


def power_out(r: PowerReport) -> PowerOut:
    return PowerOut(
        has_source=r.has_source, snap_at=r.snap_at, source_date=r.source_date, stale=r.stale,
        total_mw=r.total_mw, units_working=r.units_working, units_reserve=r.units_reserve,
        units_repair=r.units_repair,
        stations=[PowerStationOut(branch_id=s.branch_id, branch_name=s.branch_name,
                                  station=s.station, station_name=s.station_name,
                                  cascade_name=s.cascade_name, power_mw=s.power_mw,
                                  units_working=s.units_working, units_reserve=s.units_reserve,
                                  units_repair=s.units_repair) for s in r.stations])
