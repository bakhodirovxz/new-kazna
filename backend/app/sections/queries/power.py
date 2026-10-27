"""«Текущая мощность» — pub.power_latest (foydalanuvchi ko'ra oladigan eng oxirgi snapshot).

Eskirganlik: hozir − snap_at > askue.live_stale_minutes. Snapshot yo'q — manba ulanmagan.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.sections.queries.cash import num
from app.sections.scope import BranchSel


@dataclass(frozen=True, slots=True)
class PowerStation:
    branch_id: int
    branch_name: str
    station: str
    station_name: str
    cascade_name: str
    power_mw: float
    units_working: int
    units_reserve: int
    units_repair: int


@dataclass(frozen=True, slots=True)
class PowerReport:
    snap_at: datetime | None
    source_date: str | None
    stale: bool
    stations: list[PowerStation]

    @property
    def has_source(self) -> bool:
        return self.snap_at is not None

    @property
    def total_mw(self) -> float:
        return round(sum(s.power_mw for s in self.stations), 4)

    @property
    def units_working(self) -> int:
        return sum(s.units_working for s in self.stations)

    @property
    def units_reserve(self) -> int:
        return sum(s.units_reserve for s in self.stations)

    @property
    def units_repair(self) -> int:
        return sum(s.units_repair for s in self.stations)


def latest_at(db: Session) -> datetime | None:
    value = db.execute(text("SELECT max(snap_at) FROM pub.power_latest")).scalar_one()
    return value if isinstance(value, datetime) else None


def load(db: Session, sel: BranchSel, *, now: datetime, stale_minutes: int) -> PowerReport:
    latest = latest_at(db)
    if latest is None:
        return PowerReport(None, None, False, [])
    where, params = sel.rows("p.branch_id")
    rows = db.execute(text(
        "SELECT p.branch_id, b.name AS branch_name, p.station, p.station_name, p.cascade_name, "
        "p.power_mw, p.units_working, p.units_reserve, p.units_repair, p.source_date "
        "FROM pub.power_latest p JOIN pub.branches b ON b.branch_id = p.branch_id "
        f"WHERE {where} ORDER BY p.power_mw DESC, p.station"), params).all()
    return PowerReport(
        snap_at=latest, source_date=rows[0].source_date if rows else None,
        stale=now - latest > timedelta(minutes=stale_minutes),
        stations=[PowerStation(int(r.branch_id), r.branch_name, r.station, r.station_name,
                               r.cascade_name, num(r.power_mw), int(r.units_working),
                               int(r.units_reserve), int(r.units_repair)) for r in rows])
