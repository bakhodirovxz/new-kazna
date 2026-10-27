import codecs
from datetime import date
from decimal import Decimal

import pytest

from app.etl.banks.adapters import ADAPTERS
from app.etl.banks.canonical import CanonicalCsvAdapter
from app.etl.banks.models import BankFileError, mask
from app.etl.banks.registry import ADAPTER_NAMES

ACC = "20210000900100000001"
HEAD = "row_type;account;date;doc_id;direction;amount;counterparty_inn;counterparty_name;item_code"
ORDERS = ("doc_id;account;date;status;status_date;amount;counterparty_inn;"
          "counterparty_name;item_code")


def csv_bytes(lines: list[str], *, bom: bool = False) -> bytes:
    return (codecs.BOM_UTF8 if bom else b"") + ("\n".join(lines) + "\n").encode("utf-8")


def test_statement_parsed_with_bom() -> None:
    p = CanonicalCsvAdapter().parse(csv_bytes([
        HEAD,
        f"OB;{ACC};2026-09-22;;;1000000000.00;;;",
        f"L;{ACC};2026-09-22;D-1;in;250000000.00;301234567;ООО «Покупатель»;PKM54-I06",
        f"L;{ACC};2026-09-22;D-2;OUT;50000000.5;;Иванов Иван;",
        f"CB;{ACC};2026-09-22;;;1199999999.50;;;",
    ], bom=True), "sqb/v.csv")
    assert p.kind == "statement" and p.errors == []
    assert [(b.kind, b.amount) for b in p.balances] == [("OB", Decimal("1000000000.00")),
                                                        ("CB", Decimal("1199999999.50"))]
    one, two = p.lines
    assert (one.account, one.day, one.doc_id, one.direction, one.amount) == (
        ACC, date(2026, 9, 22), "D-1", "in", Decimal("250000000.00"))
    assert (one.cp_inn, one.cp_name, one.item_code) == ("301234567", "ООО «Покупатель»",
                                                         "PKM54-I06")
    assert (two.direction, two.cp_inn, two.cp_name, two.item_code, two.line) == (
        "out", None, "Иванов Иван", None, 4)


def test_columns_in_any_order_and_spaced_account() -> None:
    p = CanonicalCsvAdapter().parse(csv_bytes([
        "account;row_type;date;amount;doc_id;direction;item_code;counterparty_name;"
        "counterparty_inn",
        "2021 0000 9001 0000 0001;CB;2026-09-22;5.00;;;;;",
    ]), "x.csv")
    assert p.errors == [] and p.balances[0].account == ACC


def test_orders_parsed() -> None:
    p = CanonicalCsvAdapter().parse(csv_bytes([
        ORDERS,
        f"P-1;{ACC};2026-09-22;executed;2026-09-22;50000000.50;;;PKM54-O09",
        f"P-2;{ACC};2026-09-23;Rejected;;7000000;301234567;ООО «Покупатель»;",
        f"P-3;{ACC};2026-09-23;accepted;2026-09-24;1.00;;;",
    ]), "sqb/o.csv")
    assert p.kind == "orders" and p.errors == []
    assert [(o.doc_id, o.status, o.status_day) for o in p.orders] == [
        ("P-1", "исполнено", date(2026, 9, 22)), ("P-2", "отклонено", None),
        ("P-3", "отправлено в банк", date(2026, 9, 24))]


def test_malformed_rows_are_reported_not_fatal() -> None:
    p = CanonicalCsvAdapter().parse(csv_bytes([
        HEAD,
        f"L;{ACC};2026-09-22;D-1;in;10.00;;;",                     # 2 — to'g'ri
        f"L;{ACC};2026-09-22;D-2;in;10.00;;;;extra",               # 3 — ortiqcha maydon
        f"L;{ACC};24.09.2026;D-3;in;10.00;;;",                     # 4 — sana
        f"L;{ACC};2026-09-22;D-4;in;1 000.00;;;",                  # 5 — razryad ajratkichi
        f"L;{ACC};2026-09-22;D-5;in;10,50;;;",                     # 6 — vergulli kasr
        f"L;{ACC};2026-09-22;D-6;sideways;10.00;;;",               # 7 — yo'nalish
        f"L;{ACC};2026-09-22;D-7;out;0;;;",                        # 8 — nol summa
        f"L;{ACC[:-1]};2026-09-22;D-8;in;10.00;;;",                # 9 — 19 raqamli hisob
        f"X;{ACC};2026-09-22;D-9;in;10.00;;;",                     # 10 — row_type
        f"L;{ACC};2026-09-22;;in;10.00;;;",                        # 11 — doc_id bo'sh
        f"L;{ACC};2026-09-22;D-10;in;10.00;12345;;",               # 12 — INN formati
        "",                                                         # bo'sh qator — e'tiborsiz
        f"CB;{ACC};2026-09-22;;;-5.00;;;",                          # 14 — manfiy qoldiq mumkin
    ]), "sqb/bad.csv")
    assert [x.doc_id for x in p.lines] == ["D-1"]
    assert [b.amount for b in p.balances] == [Decimal("-5.00")]
    assert [e.line for e in p.errors] == [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    text = " | ".join(e.message for e in p.errors)
    for needle in ("полей", "дата", "разделител", "сумма", "direction", "больше нуля",
                   "20 цифр", "row_type", "doc_id", "counterparty_inn"):
        assert needle in text, needle
    assert ACC[:-1] not in text and ACC not in text


@pytest.mark.parametrize(("data", "code"), [
    (b"code;name\nT-1;x\n", "bad_header"),
    (f"{HEAD}\nL;{ACC};2026-09-22;D;in;1;;Тест;\n".encode("cp1251"), "bad_encoding"),
    (b"", "bad_header"),
    (b"a;b;c\n1;2;3\n", "bad_header"),
])
def test_file_level_errors(data: bytes, code: str) -> None:
    with pytest.raises(BankFileError) as exc:
        CanonicalCsvAdapter().parse(data, "sqb/f.csv")
    assert exc.value.code == code


def test_mask_and_registry() -> None:
    assert mask(f"выписка_{ACC}_0922.csv") == "выписка_…0001_0922.csv"
    assert mask("строка 12, сумма 1000") == "строка 12, сумма 1000"
    assert tuple(ADAPTERS) == ADAPTER_NAMES
