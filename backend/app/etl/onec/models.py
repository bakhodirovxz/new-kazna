"""1C javoblarini pydantic modeliga o'tkazish: xato matni faqat yo'l (loc) va xabar."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from app.etl.onec.client import OneCFormatError


def parse[T: BaseModel](model: type[T], data: Any, what: str) -> T:
    try:
        return model.model_validate(data)
    except PydanticValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"])
        raise OneCFormatError(f"1С {what}: неожиданная структура ({loc} — {first['msg']})") \
            from exc
