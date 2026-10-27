"""«Ввод данных» obyektlar reyestri: har obyekt bitta 2-reja `Target` ga moslanadi.

Maydon nomlari = `Target.allowed_keys` (FileConnector kanonik CSV sarlavhalari), shuning uchun
UI formasi, shablon va ops fayli bitta formatda. Bu modul faqat metadata -- tekshiruv
`validate.py`da, saqlash `store.py`da.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from app.auth.permissions import Section
from app.core.crypto import Purpose
from app.dwh.dates import date_id
from app.dwh.targets import TARGETS
from app.etl.codes import bank_account_code

FieldKind = Literal[
    "money", "volume", "int", "decimal", "pct", "date", "month", "text", "enum", "ref", "secret"
]
MONEY_LIMIT = Decimal(10) ** 15

# S2 bank ro'yxati (ruscha nomlar; dim_bank.bank_name shu matnni oladi).
BANK_NAMES = (
    "Узпромстройбанк (SQB)",
    "Национальный банк ВЭД (НБУ)",
    "Асакабанк",
    "Ипотека-банк",
    "Народный банк (Xalq)",
)
CURRENCIES = ("UZS", "USD", "EUR", "RUB", "CNY", "JPY")


@dataclass(frozen=True, slots=True)
class FieldDef:
    name: str
    kind: FieldKind
    title: str
    required: bool = True
    lo: Decimal | None = None
    hi: Decimal | None = None
    options: tuple[tuple[str, str], ...] = ()
    ref: str | None = None
    ref_where: str | None = None  # faqat koddan: dim qatorlarini toraytiruvchi SQL sharti
    purpose: Purpose | None = None
    pattern: str | None = None
    unit: str = ""


@dataclass(frozen=True, slots=True)
class ManualEntity:
    id: str
    section: Section
    title: str
    target: str
    doc_type: str | None
    fields: tuple[FieldDef, ...]
    grain: tuple[str, ...]
    code_prefix: str | None = None
    code_fn: Callable[[Mapping[str, Any]], str] | None = None
    layout: Literal["form", "grid"] = "form"
    grid: tuple[str, str, str] | None = None
    future_days: int = 0

    @property
    def kind(self) -> Literal["dim", "fact"]:
        return TARGETS[self.target].kind

    @property
    def date_field(self) -> FieldDef | None:
        return next((f for f in self.fields if f.kind in ("date", "month")), None)

    @property
    def secrets(self) -> tuple[FieldDef, ...]:
        return tuple(f for f in self.fields if f.kind == "secret")


def _opts(*values: str) -> tuple[tuple[str, str], ...]:
    return tuple((v, v) for v in values)


_BRANCH = FieldDef("branch_code", "ref", "Филиал", ref="dim_branch")

_ALL: tuple[ManualEntity, ...] = (
    ManualEntity(
        "kazna.bank_account", Section.KAZNA, "Банковские счета", "dim_bank", None,
        (
            _BRANCH,
            FieldDef("bank_name", "enum", "Банк", options=_opts(*BANK_NAMES)),
            FieldDef("account_number", "secret", "Номер счёта", purpose=Purpose.BANK,
                     pattern=r"^[0-9]{20}$"),
            FieldDef("currency", "enum", "Валюта", options=_opts(*CURRENCIES)),
        ),
        ("code",), code_fn=lambda v: bank_account_code(str(v["account_number"])),
    ),
    ManualEntity(
        "kazna.balance", Section.KAZNA, "Остатки на счетах", "fact_balance", "manual_balance",
        (
            _BRANCH,
            FieldDef("bank_code", "ref", "Счёт", ref="dim_bank"),
            FieldDef("date", "date", "Дата"),
            FieldDef("balance", "money", "Остаток", lo=-MONEY_LIMIT, hi=MONEY_LIMIT,
                     unit="млн сум"),
        ),
        ("branch_code", "bank_code", "date:month"),
    ),
    ManualEntity(
        "kazna.payment_plan", Section.KAZNA, "План платежей (бюджет)", "fact_payment_plan",
        "manual_plan",
        (
            _BRANCH,
            FieldDef("item_code", "ref", "Статья", ref="dim_item", ref_where="direction = 'out'"),
            FieldDef("date", "month", "Месяц"),
            FieldDef("amount", "money", "Сумма", lo=Decimal(0), hi=MONEY_LIMIT, unit="млн сум"),
        ),
        ("branch_code", "item_code", "date:month"),
        layout="grid", grid=("item_code", "date", "amount"), future_days=366,
    ),
)

ENTITIES: dict[str, ManualEntity] = {e.id: e for e in _ALL}
MANUAL_TARGETS: frozenset[str] = frozenset(e.target for e in _ALL)


def _as_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _grain_part(entity: ManualEntity, part: str, values: Mapping[str, Any]) -> str:
    name, _, mode = part.partition(":")
    if name == "code" and "code" not in values:
        if entity.code_fn is None:
            raise ValueError(f"{entity.id}: kod hosil qilib bo'lmaydi")
        return entity.code_fn(values)
    value = values[name]
    if mode == "month":
        return _as_date(value).strftime("%Y%m")
    return _as_date(value).isoformat() if isinstance(value, date) else str(value)


def business_key(entity: ManualEntity, values: Mapping[str, Any]) -> str:
    return "|".join(_grain_part(entity, g, values) for g in entity.grain)


def payload_for_target(
    entity: ManualEntity, values: Mapping[str, Any], *, entry_id: int, code: str | None
) -> dict[str, Any]:
    """Staging `sink.add` uchun qator. Sezgir maydon (agar `values`da bo'lsa) ochiq beriladi --
    `protect()` darhol qayta shifrlaydi; bu funksiya natijasi hech qachon saqlanmaydi."""
    target = TARGETS[entity.target]
    keep = target.allowed_keys
    out: dict[str, Any] = {k: v for k, v in values.items() if k in keep}
    if entity.kind == "dim":
        out["code"] = code
        for spec in target.sensitive:
            plain = values.get(spec.field)
            if spec.field == "account_number" and plain:
                out["account_last4"] = "".join(ch for ch in str(plain) if ch.isdigit())[-4:]
        return out
    field = entity.date_field
    if field is not None:
        day = _as_date(values[field.name])
        out["date_id"] = date_id(day.replace(day=1) if field.kind == "month" else day)
    out["src_id"] = f"M:{entry_id}"
    out["doc_type"] = entity.doc_type
    return out
