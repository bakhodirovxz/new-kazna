"""AI-анализ API sxemalari (S5 spec 4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.sections.deps import PER_PATTERN

Preset = Literal["yoy", "risks", "priorities", "plan"]


class AiAnalyzeIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    section: str = Field(pattern=r"^[a-z]{3,16}$")
    page: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    br: int | None = Field(default=None, ge=1)
    per: str = Field(default="ytd", pattern=PER_PATTERN)
    scen: Literal["base", "water", "tariff", "fx"] = "base"
    preset: Preset | None = None
    question: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("question")
    @classmethod
    def _printable(cls, value: str | None) -> str | None:
        if value is not None and any(not (ch.isprintable() or ch == "\n") for ch in value):
            raise ValueError("question")
        return value

    @model_validator(mode="after")
    def _one_prompt(self) -> AiAnalyzeIn:
        if self.preset is not None and self.question is not None:
            raise ValueError("preset va question birga yuborilmaydi")
        return self


class AiStatusOut(BaseModel):
    enabled: bool
    reason: Literal["disabled", "not_configured"] | None
    user_per_hour: int
    org_per_day: int
    used_last_hour: int


class AiRequestOut(BaseModel):
    id: int
    created_at: datetime
    finished_at: datetime | None
    username: str
    section: str
    page: str
    filters: dict[str, Any]
    preset: str | None
    question: str | None
    status: str
    error_code: str | None
    context_chars: int
    answer_chars: int
    model: str
    duration_ms: int | None
