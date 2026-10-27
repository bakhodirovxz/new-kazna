"""1C javoblarining qat'iy modellari (spec 3.1): kutilgan kalit va majburiy maydonlar tekshiriladi,
qo'shimcha maydonlar e'tiborsiz. Summalar — butun son, Decimal yoki "123.45" satri; razryad
ajratkichi yoki vergul — xato. Sana — "YYYY-MM-DD" (ixtiyoriy "T00:00:00")."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints
from pydantic import ValidationError as PydanticValidationError

from app.etl.onec.client import OneCFormatError

_MONEY_RE = re.compile(r"^-?\d+(\.\d+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?$")


def _money(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("summa mantiqiy qiymat bo'lishi mumkin emas")
    if isinstance(value, int | Decimal):
        return Decimal(value)
    if isinstance(value, str) and _MONEY_RE.fullmatch(value.strip()):
        return Decimal(value.strip())
    raise ValueError("summa formati noto'g'ri")


def _day(value: Any) -> date:
    if isinstance(value, str) and _DATE_RE.fullmatch(value):
        return date.fromisoformat(value[:10])
    raise ValueError("sana formati noto'g'ri (ГГГГ-ММ-ДД)")


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:300] or None


Money = Annotated[Decimal, BeforeValidator(_money)]
Day = Annotated[date, BeforeValidator(_day)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
OptName = Annotated[str | None, BeforeValidator(_optional_text)]


class _In(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class Payment(_In):
    number: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    doc_date: Day = Field(alias="date")
    amount: Money = Field(alias="sum")
    contractor_name: OptName = None
    contract_number: OptName = None
    expense_type_name: Name


class PaymentsResponse(_In):
    payments: list[Payment]


class IncomeRow(_In):
    org_name: Name
    direction_name: Name
    amount: Money = Field(alias="sum")
    doc_date: Day = Field(alias="date")


class IncomeResponse(_In):
    items: list[IncomeRow]


class BudgetPlanRow(_In):
    org_name: Name
    expense_type_name: Name
    month: Annotated[int, Field(strict=True, ge=1, le=12)]
    plan_sum: Money


class BudgetPlanResponse(_In):
    items: list[BudgetPlanRow]


def parse[T: BaseModel](model: type[T], data: Any, path: str) -> T:
    try:
        return model.model_validate(data)
    except PydanticValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise OneCFormatError(
            f"1С {path}: неожиданная структура ответа ({exc.error_count()} ошибок; "
            f"первая: {where} — {first['msg']})") from exc
