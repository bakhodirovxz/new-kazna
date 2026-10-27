"""«Ввод данных» tekshiruv qatlami: reyestrdan quriladigan pydantic modellar, sana oralig'i,
yopiq davr, reference mavjudligi, so'rov ichidagi biznes-kalit takrorlanishi.

Xato elementi: {"row": 1-based, "field": nomi, "code": ...}. Kiritilgan QIYMAT hech qachon
xatoga, logga yoki istisno matniga qo'yilmaydi (hisob raqami!) -- faqat maydon nomi va kod.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from functools import cache
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    ValidationError,
    create_model,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import sysconfig
from app.core.errors import ValidationFailed
from app.dwh.dates import month_start, today_tashkent
from app.manual.entities import FieldDef, ManualEntity, business_key

ItemErrors = list[dict[str, Any]]
_NUMBER = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")  # "1e5", "NaN", "1,5", "1 000" -- rad
_NO_CONTROL = re.compile(r"^[^\x00-\x1f\x7f]*$")
_REF = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_TEXT_MAX = 200


def _to_decimal(value: Any) -> Any:
    if isinstance(value, bool | float):  # float -- ikkilik xatolik
        raise ValueError("number")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str) and _NUMBER.match(value):
        try:
            return Decimal(value)
        except InvalidOperation:
            raise ValueError("number") from None
    if isinstance(value, Decimal) and value.is_finite():
        return value
    raise ValueError("number")


def _to_date(value: Any) -> Any:
    if isinstance(value, date) and not hasattr(value, "hour"):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError("date")


def _to_month(value: Any) -> Any:
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}", value):
        value = value + "-01"
    return _to_date(value).replace(day=1)


def _no_control(value: str) -> str:
    if not _NO_CONTROL.match(value):
        raise ValueError("control")
    return value


def _annotation(f: FieldDef) -> Any:
    match f.kind:
        case "money":
            return Annotated[
                Decimal,
                BeforeValidator(_to_decimal),
                Field(max_digits=20, decimal_places=2, allow_inf_nan=False,
                      ge=f.lo, le=f.hi),
            ]
        case "volume" | "decimal":
            return Annotated[
                Decimal,
                BeforeValidator(_to_decimal),
                Field(max_digits=20, decimal_places=3, allow_inf_nan=False,
                      ge=f.lo, le=f.hi),
            ]
        case "pct":
            return Annotated[
                Decimal,
                BeforeValidator(_to_decimal),
                Field(max_digits=8, decimal_places=5, ge=f.lo or Decimal(0),
                      le=f.hi or Decimal(1)),
            ]
        case "int":
            return Annotated[int, Field(strict=True, ge=f.lo, le=f.hi)]
        case "date":
            return Annotated[date, BeforeValidator(_to_date)]
        case "month":
            return Annotated[date, BeforeValidator(_to_month)]
        case "text":
            return Annotated[
                str,
                StringConstraints(min_length=1, max_length=_TEXT_MAX),
                AfterValidator(_no_control),
            ]
        case "enum":
            return Literal[tuple(code for code, _ in f.options)]
        case "ref":
            return Annotated[str, StringConstraints(pattern=_REF.pattern)]
        case "secret":
            pattern = re.compile(f.pattern or r"^.{1,64}$")

            def _check(v: SecretStr, _p: re.Pattern[str] = pattern) -> SecretStr:
                if not _p.match(v.get_secret_value()):
                    raise ValueError("pattern")
                return v

            return Annotated[SecretStr, AfterValidator(_check)]
    raise AssertionError(f.kind)  # pragma: no cover


@cache
def model_for(entity: ManualEntity) -> type[BaseModel]:
    fields: dict[str, Any] = {}
    for f in entity.fields:
        ann = _annotation(f)
        fields[f.name] = (ann, ...) if f.required else (ann | None, None)
    return create_model(
        f"Manual_{entity.id.replace('.', '_')}",
        __config__=ConfigDict(extra="forbid", strict=False, str_strip_whitespace=False),
        **fields,
    )


def to_values(model: BaseModel) -> dict[str, Any]:
    """Model -> oddiy qiymatlar (sezgir maydonlar ochiq matn -- faqat shifrlash uchun!)."""
    return {
        k: (v.get_secret_value() if isinstance(v, SecretStr) else v)
        for k, v in model.model_dump().items()
    }


def _error_code(kind: str) -> str:
    return {"missing": "required", "extra_forbidden": "unknown_field"}.get(kind, "invalid_value")


def _model_errors(exc: ValidationError, row: int) -> ItemErrors:
    return [
        {"row": row, "field": str(e["loc"][0]) if e["loc"] else "", "code": _error_code(e["type"])}
        for e in exc.errors(include_input=False, include_url=False, include_context=False)
    ]


def _locked_through(db: Session) -> tuple[int, int] | None:
    raw = str(sysconfig.current(db, "manual.locked_through") or "")
    return (int(raw[:4]), int(raw[5:7])) if raw else None


def _is_locked(locked: tuple[int, int] | None, day: date) -> bool:
    return locked is not None and (day.year, day.month) <= locked


def _as_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def assert_period_open(
    db: Session, entity: ManualEntity, values_list: list[dict[str, Any]]
) -> None:
    field = entity.date_field
    if entity.kind != "fact" or field is None:
        return
    locked = _locked_through(db)
    rows = [i + 1 for i, v in enumerate(values_list) if _is_locked(locked, _as_date(v[field.name]))]
    if rows:
        raise ValidationFailed("period_locked", fields=[field.name], rows=rows[:200])


def _branch_code(db: Session, branch_id: int) -> str | None:
    return db.execute(text("SELECT code FROM dwh.dim_branch WHERE branch_id = :b"),
                      {"b": branch_id}).scalar_one_or_none()


def _existing_refs(db: Session, entity: ManualEntity, f: FieldDef, codes: set[str]) -> set[str]:
    """dwh o'lchovi YOKI shu o'lchovni yaratuvchi tasdiqlangan (o'chirilmagan) manual bosh."""
    if not codes or f.ref is None:
        return set()
    from app.manual.entities import ENTITIES  # sikldan qochish

    where = f" AND {f.ref_where}" if f.ref_where else ""
    # f.ref/ref_where faqat reyestr kodidan (foydalanuvchi kiritmaydi); qiymatlar -- parametr.
    found = set(db.execute(
        text(f"SELECT code FROM dwh.{f.ref} WHERE code = ANY(:c){where}"),  # noqa: S608
        {"c": sorted(codes)}).scalars())
    owners = [e.id for e in ENTITIES.values() if e.kind == "dim" and e.target == f.ref]
    if owners and not f.ref_where:
        found |= set(db.execute(text(
            "SELECT code FROM core.manual_head WHERE entity = ANY(:e) AND code = ANY(:c) "
            "AND approved_version IS NOT NULL AND NOT approved_deleted"),
            {"e": owners, "c": sorted(codes)}).scalars())
    return found


def _dup_field(entity: ManualEntity) -> str:
    if entity.date_field is not None:
        return entity.date_field.name
    return entity.secrets[0].name if entity.secrets else entity.grain[-1].split(":")[0]


def check_items(
    db: Session, entity: ManualEntity, branch_id: int, items: list[dict[str, Any]]
) -> tuple[list[BaseModel], ItemErrors]:
    model = model_for(entity)
    models: list[BaseModel | None] = []
    errors: ItemErrors = []
    for i, raw in enumerate(items, start=1):
        try:
            models.append(model.model_validate(raw))
        except ValidationError as exc:
            models.append(None)
            errors += _model_errors(exc, i)
    good = [(i, m) for i, m in enumerate(models, start=1) if m is not None]
    values = {i: to_values(m) for i, m in good}

    branch = _branch_code(db, branch_id)
    date_field = entity.date_field
    locked = _locked_through(db)
    history_start = date.fromisoformat(str(sysconfig.current(db, "etl.history_start")))
    today = today_tashkent()
    for i, v in values.items():
        if "branch_code" in v and v["branch_code"] != branch:
            errors.append({"row": i, "field": "branch_code", "code": "invalid_value"})
        if date_field is None or entity.kind != "fact":
            continue
        day: date = v[date_field.name]
        if date_field.kind == "month":
            low, high = month_start(history_start), today + timedelta(days=entity.future_days)
            ok = low <= day <= high
        else:
            ok = history_start <= day <= today + timedelta(days=entity.future_days)
        if not ok:
            errors.append({"row": i, "field": date_field.name, "code": "invalid_value"})
        elif _is_locked(locked, day):
            errors.append({"row": i, "field": date_field.name, "code": "period_locked"})

    for f in entity.fields:
        if f.kind != "ref" or f.name == "branch_code":
            continue
        wanted = {str(v[f.name]) for v in values.values() if v.get(f.name)}
        known = _existing_refs(db, entity, f, wanted)
        errors += [{"row": i, "field": f.name, "code": "reference_not_found"}
                   for i, v in values.items() if v.get(f.name) and str(v[f.name]) not in known]

    seen: set[str] = set()
    for i, v in values.items():
        key = business_key(entity, v)
        if key in seen:
            errors.append({"row": i, "field": _dup_field(entity), "code": "duplicate_record"})
        seen.add(key)
    if errors:
        return [], sorted(errors, key=lambda e: (e["row"], e["field"]))
    return [m for m in models if m is not None], []


__all__ = ["ItemErrors", "assert_period_open", "check_items", "model_for", "to_values"]
