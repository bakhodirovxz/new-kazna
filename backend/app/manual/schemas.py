"""«Ввод данных» API sxemalari. Sezgir qiymat HECH QACHON javobda: faqat niqob ("…1234")."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_ITEMS = 500
MAX_IMPORT_ROWS = 5000


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


class PublicationCheck(BaseModel):
    code: str
    items: list[dict[str, int]] = Field(default_factory=list)  # branch_id / month_id / date_id


class PublicationOut(BaseModel):
    """Nashr holati -- o'qilganda hisoblanadi (paket `status` i o'zgarmaydi)."""

    status: Literal["none", "queued", "running", "published", "failed"]
    build_id: int | None = None
    run_id: int | None = None
    kind: Literal["quality", "build"] | None = None
    error: str | None = None
    checks: list[PublicationCheck] = Field(default_factory=list)


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
    publication: PublicationOut | None = None


class ChangeOut(BaseModel):
    entry_id: int
    version: int
    op: Literal["add", "change", "delete"]
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class BatchDetailOut(BatchOut):
    items: list[ChangeOut]


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int


class OptionOut(BaseModel):
    code: str
    title: str


class FieldOut(BaseModel):
    name: str
    kind: str
    title: str
    required: bool
    lo: str | None = None
    hi: str | None = None
    options: list[OptionOut] = Field(default_factory=list)
    ref: str | None = None
    unit: str = ""


class EntityOut(BaseModel):
    id: str
    section: str
    section_title: str
    title: str
    kind: Literal["dim", "fact"]
    layout: Literal["form", "grid"]
    grid: tuple[str, str, str] | None = None
    fields: list[FieldOut]
    can_write: bool
    can_approve: bool


class RecordOut(BaseModel):
    entry_id: int
    version: int
    branch_id: int
    values: dict[str, Any]
    masks: dict[str, str]
    status: Literal["active", "pending", "deleted"]
    pending_batch_id: int | None = None
    shadowed_by: str | None = None


class HistoryVersionOut(BaseModel):
    version: int
    batch_id: int
    batch_status: str
    created_by_name: str | None
    created_at: datetime
    decided_by_name: str | None = None
    decided_at: datetime | None = None
    reason: str | None = None
    deleted: bool
    values: dict[str, Any]
    masks: dict[str, str]


class HistoryOut(BaseModel):
    versions: list[HistoryVersionOut]
