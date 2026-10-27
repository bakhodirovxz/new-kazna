import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core.db import apply_rls
from app.core.errors import ValidationFailed
from app.manual.entities import ENTITIES
from app.manual.validate import assert_period_open, check_items, to_values
from tests.manual_helpers import (
    balance_item,
    bank_account_item,
    branch_code,
    migrator_sql,
    plan_item,
    seed_dwh_bank,
)

BAL = ENTITIES["kazna.balance"]
BANK = "BA-t4bank0000000001"
Setting = Callable[[str, object], None]


@pytest.fixture
def app_db(db: Session) -> Session:
    apply_rls(db, None)
    seed_dwh_bank(BANK)
    return db


def _codes(errors: list[dict[str, Any]]) -> set[tuple[int, str, str]]:
    return {(e["row"], e["field"], e["code"]) for e in errors}


def test_money_bounds_and_scale(app_db: Session) -> None:
    item = balance_item(BANK, "2026-09-30", "12345.678")
    models, errors = check_items(app_db, BAL, 1, [item])
    assert not models and _codes(errors) == {(1, "balance", "invalid_value")}
    for bad in ("1e5", "NaN", "9" * 16, 12.5):
        item["balance"] = bad
        assert check_items(app_db, BAL, 1, [item])[1], bad


def test_negative_balance_allowed(app_db: Session) -> None:
    models, errors = check_items(app_db, BAL, 1, [balance_item(BANK, "2026-09-30", "-5.50")])
    assert not errors and str(to_values(models[0])["balance"]) == "-5.50"


def test_month_normalized(app_db: Session) -> None:
    models, errors = check_items(app_db, ENTITIES["kazna.payment_plan"], 1,
                                 [plan_item("PKM54-O09", "2026-09", "10")])
    assert not errors and to_values(models[0])["date"].isoformat() == "2026-09-01"


def test_future_date_refused_for_balance(app_db: Session) -> None:
    _, errors = check_items(app_db, BAL, 1, [balance_item(BANK, "2999-01-01", "1")])
    assert _codes(errors) == {(1, "date", "invalid_value")}
    _, errors = check_items(app_db, BAL, 1, [balance_item(BANK, "2000-01-01", "1")])
    assert _codes(errors) == {(1, "date", "invalid_value")}  # etl.history_start dan oldin


def test_period_locked(app_db: Session, setting: Setting) -> None:
    setting("manual.locked_through", "2026-08")
    _, errors = check_items(app_db, BAL, 1, [balance_item(BANK, "2026-08-31", "1")])
    assert _codes(errors) == {(1, "date", "period_locked")}
    models, errors = check_items(app_db, BAL, 1, [balance_item(BANK, "2026-09-01", "1")])
    assert not errors
    with pytest.raises(ValidationFailed) as exc:
        assert_period_open(app_db, BAL, [{"date": "2026-08-01"}])
    assert exc.value.code == "period_locked"
    assert_period_open(app_db, BAL, [to_values(models[0])])


def test_reference_must_exist_or_be_approved(app_db: Session) -> None:
    _, errors = check_items(app_db, BAL, 1, [balance_item("BA-nope", "2026-09-30", "1")])
    assert _codes(errors) == {(1, "bank_code", "reference_not_found")}
    code = f"BA-d{uuid.uuid4().hex[:15]}"
    migrator_sql(  # draft/submitted havola -- yo'q
        "INSERT INTO core.manual_head (entity, branch_id, business_key, code) "
        "VALUES ('kazna.bank_account', 1, :c, :c)", c=code)
    _, errors = check_items(app_db, BAL, 1, [balance_item(code, "2026-09-30", "1")])
    assert _codes(errors) == {(1, "bank_code", "reference_not_found")}
    migrator_sql("UPDATE core.manual_head SET approved_version = 1 WHERE code = :c", c=code)
    _, errors = check_items(app_db, BAL, 1, [balance_item(code, "2026-09-30", "1")])
    assert not errors


def test_item_ref_only_outgoing_for_plan(app_db: Session) -> None:
    _, errors = check_items(app_db, ENTITIES["kazna.payment_plan"], 1,
                            [plan_item("PKM54-I06", "2026-09", "1")])
    assert _codes(errors) == {(1, "item_code", "reference_not_found")}


def test_branch_code_must_match_batch_branch(app_db: Session) -> None:
    item = balance_item(BANK, "2026-09-30", "1", branch_id=2)
    _, errors = check_items(app_db, BAL, 1, [item])
    assert _codes(errors) == {(1, "branch_code", "invalid_value")}
    assert branch_code(1) != branch_code(2)


def test_text_control_chars_and_secret_pattern(app_db: Session) -> None:
    item = bank_account_item(1)
    item["bank_name"] = "Асака\x00банк"
    assert _codes(check_items(app_db, ENTITIES["kazna.bank_account"], 1, [item])[1]) == {
        (1, "bank_name", "invalid_value")}
    item = bank_account_item(1, number="123")
    _, errors = check_items(app_db, ENTITIES["kazna.bank_account"], 1, [item])
    assert _codes(errors) == {(1, "account_number", "invalid_value")}
    assert "123" not in str(errors)


def test_extra_field_forbidden_and_missing(app_db: Session) -> None:
    item = balance_item(BANK, "2026-09-30", "1")
    item["evil"] = "x"
    del item["balance"]
    _, errors = check_items(app_db, BAL, 1, [item])
    assert _codes(errors) == {(1, "evil", "unknown_field"), (1, "balance", "required")}


def test_duplicate_business_key_in_request(app_db: Session) -> None:
    a = balance_item(BANK, "2026-09-30", "1")
    b = balance_item(BANK, "2026-09-01", "2")
    _, errors = check_items(app_db, BAL, 1, [a, b])
    assert _codes(errors) == {(2, "date", "duplicate_record")}
