"""Meta API javoblari."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class BranchOut(BaseModel):
    id: int
    code: str
    name: str
    short_name: str
    kind: str
    is_hq: bool
    capacity_mw: float | None
    lat: float | None
    lon: float | None


class PeriodOut(BaseModel):
    code: str
    kind: str
    label: str
    date_from: date
    date_to: date


class PeriodsOut(BaseModel):
    default: str
    today: date
    items: list[PeriodOut]


class MenuPageOut(BaseModel):
    id: str
    title: str


class MenuSectionOut(BaseModel):
    id: str
    title: str
    pages: list[MenuPageOut]


class MenuGroupOut(BaseModel):
    title: str | None
    sections: list[MenuSectionOut]


class MenuOut(BaseModel):
    groups: list[MenuGroupOut]


class FreshnessOut(BaseModel):
    last_success_at: datetime | None
    stale: bool
    max_age_hours: int
    active_build_id: int | None
