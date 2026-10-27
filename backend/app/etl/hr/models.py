"""HR API javoblari — faqat agregatlar (TZ 9). Har qator faqat oq ro'yxatdagi kalitlardan
o'qiladi; boshqa kalitlar (ФИО, ПИНФЛ, tabel raqami va h.k.) umuman o'qilmaydi, saqlanmaydi,
log'ga yozilmaydi. `name` kaliti toifa sifatida QABUL QILINMAYDI — xodimlar ro'yxatidagi ism
toifa deb adashib saqlanmasin.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.etl.hr.client import HrApiError

_LIST_KEYS = ("data", "items", "results")
_ORG = ("organization", "organization_name", "org_name", "org")
_CATEGORY = ("category", "category_name", "position_category")
_EMPLOYEES = ("employees_count", "employee_count", "count", "total")
_STAFF = ("staff_units", "staff_count")
_HIRED = ("hired", "hired_count")
_FIRED = ("fired", "fired_count", "dismissed")
_OVERTIME = ("overtime_hours",)


class HrFormatError(HrApiError):
    """Javob tuzilmasi kutilganidek emas (qiymatlar xato matniga yozilmaydi)."""


@dataclass(frozen=True, slots=True)
class BreakdownRow:
    organization: str | None
    category: str
    employees: int
    staff: Decimal | None
    hired: int | None
    fired: int | None
    overtime: Decimal | None


def _first(item: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
    return None


def _number(value: Any, line: int) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise HrFormatError(f"строка {line}: ожидается число")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise HrFormatError(f"строка {line}: ожидается число") from exc
    if not number.is_finite() or number < 0:
        raise HrFormatError(f"строка {line}: отрицательное или недопустимое число")
    return number


def _int(value: Any, line: int) -> int | None:
    number = _number(value, line)
    return None if number is None else int(number)


def parse_main(data: Any) -> int | None:
    if not isinstance(data, Mapping):
        return None
    value = _first(data, ("total_employees_count", "total_count"))
    try:
        return _int(value, 0)
    except HrFormatError:
        return None


def _items(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, Mapping):
        for key in _LIST_KEYS:
            if isinstance(data.get(key), list):
                return list(data[key])
        if data and all(isinstance(v, int | float) and not isinstance(v, bool)
                        for v in data.values()):
            return [{"category": k, "count": v} for k, v in data.items()]
    raise HrFormatError("HR API: неожиданная структура ответа (ожидается список агрегатов)")


def parse_breakdown(data: Any) -> list[BreakdownRow]:
    rows: list[BreakdownRow] = []
    for line, item in enumerate(_items(data), start=1):
        if not isinstance(item, Mapping):
            raise HrFormatError(f"строка {line}: ожидается объект")
        category = _first(item, _CATEGORY)
        employees = _int(_first(item, _EMPLOYEES), line)
        if not isinstance(category, str) or not category.strip() or employees is None:
            raise HrFormatError(f"строка {line}: нет категории или численности")
        org = _first(item, _ORG)
        rows.append(BreakdownRow(
            organization=org.strip()[:200] if isinstance(org, str) and org.strip() else None,
            category=category.strip()[:100], employees=employees,
            staff=_number(_first(item, _STAFF), line), hired=_int(_first(item, _HIRED), line),
            fired=_int(_first(item, _FIRED), line),
            overtime=_number(_first(item, _OVERTIME), line)))
    return rows
