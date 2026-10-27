"""Kanonik bank CSV (docs/integration/banks-format.md; TZ 8 «Общие правила обмена»):
UTF-8 (BOM ixtiyoriy), ';', sanalar ГГГГ-ММ-ДД, summalar nuqta bilan, razryad ajratkichsiz.
Sarlavha to'plami (tartibi erkin) fayl turini belgilaydi. Qator xatosi faylni to'xtatmaydi —
`ParsedFile.errors` ga yoziladi; kodlash/sarlavha xatosi — `BankFileError` (butun fayl).
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date
from decimal import Decimal

from app.etl.banks.models import (
    BalanceRow,
    BankFileError,
    Direction,
    FileKind,
    LineRow,
    OrderRow,
    ParsedFile,
    RowError,
    mask,
    normalize_account,
)

STATEMENT_COLUMNS = ("row_type", "account", "date", "doc_id", "direction", "amount",
                     "counterparty_inn", "counterparty_name", "item_code")
ORDER_COLUMNS = ("doc_id", "account", "date", "status", "status_date", "amount",
                 "counterparty_inn", "counterparty_name", "item_code")
STATUSES = {"accepted": "отправлено в банк", "executed": "исполнено", "rejected": "отклонено"}
MAX_ROWS = 200_000
_AMOUNT = re.compile(r"^-?\d{1,15}(\.\d{1,2})?$")
_THOUSANDS = re.compile(r"^-?\d{1,3}([\s\xa0\N{NARROW NO-BREAK SPACE}']\d{3})+([.,]\d+)?$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ACCOUNT = re.compile(r"^\d{20}$")
_DOC_ID = re.compile(r"^[0-9A-Za-z._/-]{1,64}$")
_INN = re.compile(r"^(\d{9}|\d{14})$")
_ITEM = re.compile(r"^[0-9A-Za-z._-]{1,32}$")


def _day(value: str, name: str) -> date:
    if not _DATE.fullmatch(value):
        raise ValueError(f"{name}: неверная дата «{value[:12]}» (ожидается ГГГГ-ММ-ДД)")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name}: неверная дата «{value[:12]}»") from exc


def _amount(value: str) -> Decimal:
    if _THOUSANDS.fullmatch(value):
        raise ValueError(f"amount: разделитель разрядов в сумме «{value[:20]}» не допускается")
    if not _AMOUNT.fullmatch(value):
        raise ValueError(f"amount: неверная сумма «{value[:20]}» (точка, до 2 знаков)")
    return Decimal(value)


def _account(value: str) -> str:
    account = normalize_account(value)
    if not _ACCOUNT.fullmatch(account):
        # Qiymatning o'zi xabarga qo'yilmaydi (hisob raqami bo'lishi mumkin).
        raise ValueError("account: ожидается 20 цифр расчётного счёта")
    return account


def _optional(value: str, pattern: re.Pattern[str], name: str) -> str | None:
    if not value:
        return None
    if not pattern.fullmatch(value):
        raise ValueError(f"{name}: неверный формат")
    return value


def _doc_id(value: str) -> str:
    if not _DOC_ID.fullmatch(value):
        raise ValueError("doc_id: пусто или недопустимые символы (A-Z, 0-9, . _ / -)")
    return value


class CanonicalCsvAdapter:
    name = "canonical"

    def parse(self, data: bytes, name: str) -> ParsedFile:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise BankFileError("bad_encoding", f"{name}: файл не в кодировке UTF-8") from exc
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=";")
        header = next(reader, None)
        columns = [h.strip().lower() for h in header or []]
        kind: FileKind
        if sorted(columns) == sorted(STATEMENT_COLUMNS):
            kind = "statement"
        elif sorted(columns) == sorted(ORDER_COLUMNS):
            kind = "orders"
        else:
            raise BankFileError("bad_header",
                                f"{name}: заголовок не соответствует формату (см. banks-format)")
        out = ParsedFile(kind)
        for line, raw in enumerate(reader, start=2):
            if line > MAX_ROWS + 1:
                raise BankFileError("too_many_rows", f"{name}: более {MAX_ROWS} строк")
            if not any(cell.strip() for cell in raw):
                continue
            if len(raw) != len(columns):
                out.errors.append(RowError(line, f"ожидается {len(columns)} полей, "
                                                 f"получено {len(raw)}"))
                continue
            row = dict(zip(columns, (cell.strip() for cell in raw), strict=True))
            try:
                if kind == "statement":
                    self._statement(line, row, out)
                else:
                    self._order(line, row, out)
            except ValueError as exc:
                out.errors.append(RowError(line, mask(str(exc))))
        return out

    @staticmethod
    def _statement(line: int, row: dict[str, str], out: ParsedFile) -> None:
        row_type = row["row_type"].upper()
        if row_type not in ("OB", "CB", "L"):
            raise ValueError(f"row_type: ожидается OB, CB или L, получено «{row_type[:5]}»")
        account = _account(row["account"])
        day = _day(row["date"], "date")
        amount = _amount(row["amount"])
        if row_type == "OB":
            out.balances.append(BalanceRow(line, account, day, "OB", amount))
            return
        if row_type == "CB":
            out.balances.append(BalanceRow(line, account, day, "CB", amount))
            return
        doc_id = _doc_id(row["doc_id"])
        raw_direction = row["direction"].lower()
        if raw_direction not in ("in", "out"):
            raise ValueError("direction: ожидается in или out")
        direction: Direction = "in" if raw_direction == "in" else "out"
        if amount <= 0:
            raise ValueError("amount: сумма проводки должна быть больше нуля")
        out.lines.append(LineRow(
            line, account, day, doc_id, direction, amount,
            _optional(row["counterparty_inn"], _INN, "counterparty_inn"),
            row["counterparty_name"][:300] or None,
            _optional(row["item_code"], _ITEM, "item_code")))

    @staticmethod
    def _order(line: int, row: dict[str, str], out: ParsedFile) -> None:
        doc_id = _doc_id(row["doc_id"])
        account = _account(row["account"])
        day = _day(row["date"], "date")
        status = STATUSES.get(row["status"].lower())
        if status is None:
            raise ValueError("status: ожидается accepted, executed или rejected")
        status_day = _day(row["status_date"], "status_date") if row["status_date"] else None
        amount = _amount(row["amount"])
        if amount <= 0:
            raise ValueError("amount: сумма поручения должна быть больше нуля")
        out.orders.append(OrderRow(
            line, account, day, doc_id, status, status_day, amount,
            _optional(row["counterparty_inn"], _INN, "counterparty_inn"),
            row["counterparty_name"][:300] or None,
            _optional(row["item_code"], _ITEM, "item_code")))
