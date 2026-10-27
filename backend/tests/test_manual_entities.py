from datetime import date
from decimal import Decimal

import pytest

from app.dwh.targets import TARGETS
from app.etl.codes import bank_account_code, counterparty_code
from app.manual.entities import (
    ENTITIES,
    MANUAL_TARGETS,
    ManualEntity,
    business_key,
    payload_for_target,
)


@pytest.mark.parametrize("entity", list(ENTITIES.values()), ids=lambda e: e.id)
def test_fields_map_to_target_keys(entity: ManualEntity) -> None:
    target = TARGETS[entity.target]
    allowed = target.allowed_keys | {"branch_code", "account_last4"}
    assert {f.name for f in entity.fields} <= allowed | {"date"}
    assert {g.split(":")[0] for g in entity.grain} <= {f.name for f in entity.fields} | {"code"}
    secrets = {f.name for f in entity.fields if f.kind == "secret"}
    assert secrets == {s.field for s in target.sensitive}
    assert entity.kind == target.kind and entity.target in MANUAL_TARGETS


def test_mvp_entities_present() -> None:
    assert {"kazna.bank_account", "kazna.balance", "kazna.payment_plan"} <= set(ENTITIES)
    assert ENTITIES["kazna.payment_plan"].layout == "grid"


def test_business_key_month_grain() -> None:
    e = ENTITIES["kazna.balance"]
    a = business_key(e, {"branch_code": "B1", "bank_code": "BA-x", "date": date(2026, 9, 30)})
    b = business_key(e, {"branch_code": "B1", "bank_code": "BA-x", "date": date(2026, 9, 1)})
    assert a == b == "B1|BA-x|202609"


def test_payload_has_manual_src_and_doc_type() -> None:
    p = payload_for_target(
        ENTITIES["kazna.balance"],
        {"branch_code": "B1", "bank_code": "BA-x", "date": date(2026, 9, 30),
         "balance": Decimal("1500.00")},
        entry_id=7, code=None)
    assert p["src_id"] == "M:7" and p["doc_type"] == "manual_balance"
    assert p["date_id"] == 20260930 and "date" not in p and p["branch_code"] == "B1"


def test_plan_month_uses_first_day() -> None:
    p = payload_for_target(
        ENTITIES["kazna.payment_plan"],
        {"branch_code": "B1", "item_code": "PKM54-O01", "date": "2026-09-17",
         "amount": Decimal("5")}, entry_id=1, code=None)
    assert p["date_id"] == 20260901 and p["doc_type"] == "manual_plan"


def test_dim_payload_drops_branch_and_derives_last4() -> None:
    p = payload_for_target(
        ENTITIES["kazna.bank_account"],
        {"branch_code": "B1", "bank_name": "Асакабанк", "currency": "UZS",
         "account_number": "20208000123456789012"}, entry_id=3, code="BA-0123456789abcdef")
    assert "branch_code" not in p and p["code"] == "BA-0123456789abcdef"
    assert p["account_last4"] == "9012" and p["account_number"] == "20208000123456789012"


def test_bank_account_code_matches_s2_scheme() -> None:
    spaced = bank_account_code("2020 8000 1234 5678 9012")
    assert spaced == bank_account_code("20208000123456789012")
    code = bank_account_code("20208000123456789012")
    assert code.startswith("BA-") and len(code) == 19
    assert "20208000" not in code


def test_counterparty_code_requires_9_digits() -> None:
    assert counterparty_code("123456789").startswith("CP-")
    with pytest.raises(ValueError):
        counterparty_code("12345")
