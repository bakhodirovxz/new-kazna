"""«Ввод данных» API sxemalari. Sezgir qiymat HECH QACHON javobda: faqat niqob ("…1234")."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_ITEMS = 500


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ItemIn(Strict):
    entry_id: int | None = None
    expected_version: int | None = None
    values: dict[str, Any] = Field(default_factory=dict)
    delete: bool = False


class BatchIn(Strict):
    entity: str = Field(max_length=48)
    branch_id: int
    origin: Literal["form", "grid"]
    items: list[ItemIn] = Field(min_length=1, max_length=MAX_ITEMS)
    submit: bool = False
    reason: str | None = Field(default=None, max_length=500)


class BatchUpdateIn(Strict):
    expected_version: int
    items: list[ItemIn] = Field(min_length=1, max_length=MAX_ITEMS)


class SubmitIn(Strict):
    expected_version: int
    reason: str | None = Field(default=None, max_length=500)


class WithdrawIn(Strict):
    expected_version: int


class DecisionIn(Strict):
    expected_version: int
    comment: str | None = Field(default=None, max_length=500)


class BatchOut(BaseModel):
    batch_id: int
    entity: str
    branch_id: int
    status: str
    origin: str
    rows: int
    reason: str | None = None
    created_by: int
    created_at: datetime
    submitted_at: datetime | None = None
    decided_by: int | None = None
    decided_at: datetime | None = None
    decision_comment: str | None = None
    version: int
    etl_request_id: int | None = None


class ChangeOut(BaseModel):
    entry_id: int
    version: int
    op: Literal["add", "change", "delete"]
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class PublicationOut(BaseModel):
    status: Literal["none", "queued", "running", "published", "failed"]
    build_id: int | None = None


class BatchDetailOut(BatchOut):
    items: list[ChangeOut]
    publication: PublicationOut | None = None


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
