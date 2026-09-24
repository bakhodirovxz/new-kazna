from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditOut(BaseModel):
    id: int
    ts: datetime
    user_id: int | None
    username: str | None
    action: str
    result: str
    object_type: str | None
    object_id: str | None
    request_id: str | None
    details: dict[str, Any]
    ip: str | None


class VerifyOut(BaseModel):
    ok: bool
    checked: int
    bad_ids: list[int]
    first_bad_id: int | None
