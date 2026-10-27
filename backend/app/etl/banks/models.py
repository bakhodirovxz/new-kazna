"""Bank ma'lumotining manbadan mustaqil ko'rinishi: fayl adapterlari va DirectBank mijozi bir xil
`ParsedFile` qaytaradi, `BankMapper` uni staging'ga yozadi (S2 spec 3.2).

Hisob raqami bu obyektlarda ochiq (xotirada) — log/xato matnlariga faqat `mask()` orqali.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

FileKind = Literal["statement", "orders"]
Direction = Literal["in", "out"]
_LONG_DIGITS = re.compile(r"\d{10,}")


def mask(text: str) -> str:
    """10+ raqamli ketma-ketlik (hisob raqami) → «…1234»."""
    return _LONG_DIGITS.sub(lambda m: "…" + m.group()[-4:], text)


def normalize_account(value: str) -> str:
    return re.sub(r"[\s-]", "", value)


class BankFileError(ValueError):
    """Butun faylni rad etish sababi (kodlash, sarlavha, hajm)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class BalanceRow:
    line: int
    account: str
    day: date
    kind: Literal["OB", "CB"]
    amount: Decimal


@dataclass(frozen=True, slots=True)
class LineRow:
    line: int
    account: str
    day: date
    doc_id: str
    direction: Direction
    amount: Decimal
    cp_inn: str | None
    cp_name: str | None
    item_code: str | None


@dataclass(frozen=True, slots=True)
class OrderRow:
    line: int
    account: str
    day: date
    doc_id: str
    status: str
    status_day: date | None
    amount: Decimal
    cp_inn: str | None
    cp_name: str | None
    item_code: str | None


@dataclass(frozen=True, slots=True)
class RowError:
    line: int
    message: str


@dataclass
class ParsedFile:
    kind: FileKind
    balances: list[BalanceRow] = field(default_factory=list)
    lines: list[LineRow] = field(default_factory=list)
    orders: list[OrderRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
