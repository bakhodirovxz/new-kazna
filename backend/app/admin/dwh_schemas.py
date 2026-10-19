"""ETL, buildlar va versiyali sozlamalar admin sxemalari."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.dwh.reference import FIN_KEYS, FIN_YEARS


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EtlRunOut(BaseModel):
    id: int
    source: str
    mode: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    window_from: date | None
    window_to: date | None
    rows_in: int
    rows_upserted: int
    build_id: int | None
    triggered_by: int | None
    error: str | None


class EtlStepOut(BaseModel):
    name: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    rows: int
    detail: dict[str, Any]


class EtlErrorOut(BaseModel):
    step: str
    severity: str
    target: str | None
    src_id: str | None
    code: str
    message: str
    created_at: datetime


class EtlRunDetail(BaseModel):
    run: EtlRunOut
    steps: list[EtlStepOut]
    errors: list[EtlErrorOut]


class EtlRunRequest(_In):
    source: str = Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")
    mode: Literal["full", "incremental"] = "incremental"


class EtlRequestOut(BaseModel):
    request_id: int
    status: str


class BuildOut(BaseModel):
    build_id: int
    created_at: datetime
    status: str
    load_id: int | None
    published_at: datetime | None
    active: bool


class RollbackIn(_In):
    build_id: int | None = Field(default=None, gt=0)


class AlertRuleOut(BaseModel):
    code: str
    version: int
    title: str
    section: str
    page: str
    threshold: dict[str, Any]
    level: str
    enabled: bool
    updated_by: int | None
    updated_at: datetime


class AlertRuleUpdate(_In):
    value: float | None = Field(default=None, ge=-1_000_000, le=1_000_000)
    op: Literal["<", "<=", ">", ">="] | None = None
    level: Literal["critical", "warning"] | None = None
    enabled: bool | None = None


class FinAssumptionOut(BaseModel):
    scenario: str
    year: int
    key: str
    value: float
    version: int
    updated_by: int | None
    updated_at: datetime


class FinAssumptionItem(_In):
    scenario: Literal["base", "water", "tariff", "fx"]
    year: int
    key: str
    value: float = Field(ge=-10, le=10)

    @field_validator("year")
    @classmethod
    def _year(cls, value: int) -> int:
        if value not in FIN_YEARS:
            raise ValueError("year")
        return value

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        if value not in FIN_KEYS:
            raise ValueError("key")
        return value


class FinAssumptionsUpdate(_In):
    items: list[FinAssumptionItem] = Field(min_length=1, max_length=200)


class SettingOut(BaseModel):
    key: str
    value: Any
    version: int
    updated_by: int | None
    updated_at: datetime | None


class SettingUpdate(_In):
    value: Any

