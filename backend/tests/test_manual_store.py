import json
from collections.abc import Callable
from typing import Any

import pytest

from app.core.errors import AppError, ConflictError, ForbiddenError, ValidationFailed
from app.manual import store
from tests.helpers import SeedUser
from tests.manual_helpers import (
    audit_dump,
    audit_rows,
    balance_item,
    bank_account_item,
    ctx_of,
    migrator_sql,
    plan_item,
    read,
    run,
    seed_dwh_bank,
)

pytestmark = pytest.mark.usefixtures("clean_manual")
MakeUser = Callable[..., SeedUser]
BANK = "BA-t5bank0000000001"


def _item(values: dict[str, Any], **kw: Any) -> store.ItemIn:
    return store.ItemIn(values=values, **kw)


def _create(ctx, entity: str, items: list[store.ItemIn], **kw: Any):  # type: ignore[no-untyped-def]
    return run(ctx, store.create_batch, entity_id=entity, branch_id=kw.pop("branch_id", 1),
               origin="form", items=items, **kw)


@pytest.fixture
def maker(make_user: MakeUser):  # type: ignore[no-untyped-def]
    seed_dwh_bank(BANK)
    return ctx_of(make_user("spec_kazna"))


def test_create_submit_records_versions_and_audit(maker) -> None:  # type: ignore[no-untyped-def]
    batch = _create(maker, "kazna.bank_account", [_item(bank_account_item())], submit=True)
    assert batch.status == "submitted" and batch.rows == 1 and batch.version == 2
    ev = audit_rows("data.batch.submitted")[-1]
    assert ev["details"]["content_hash"] and ev["details"]["changes"][0]["op"] == "add"
    heads = migrator_sql("SELECT version, pending_batch_id, code FROM core.manual_head "
                         "WHERE entry_id = (SELECT entry_id FROM core.manual_entry "
                         "WHERE batch_id = :b)", b=batch.batch_id)
    assert heads[0][0] == 1 and heads[0][1] == batch.batch_id and heads[0][2].startswith("BA-")


def test_account_number_never_returned_or_audited(maker, caplog) -> None:  # type: ignore[no-untyped-def]
    plain = "20208000123456789012"
    batch = _create(maker, "kazna.bank_account",
                    [_item(bank_account_item(number=plain))], submit=True)
    detail = read(maker, store.get_batch, batch.batch_id)
    dumped = batch.model_dump_json() + detail.model_dump_json() + audit_dump() + caplog.text
    assert plain not in dumped and "9012" in detail.model_dump_json()
    row = migrator_sql("SELECT bank_enc, payload::text, masks::text FROM core.manual_entry "
                       "WHERE batch_id = :b", b=batch.batch_id)[0]
    assert plain.encode() not in bytes(row[0]) and plain not in row[1] and plain not in row[2]
    assert json.loads(row[2]) == {"account_number": "…9012"}


def test_encrypted_with_row_bound_aad(maker) -> None:  # type: ignore[no-untyped-def]
    from app.core import keystore
    from app.core.crypto import Purpose

    plain = "20208000123456780001"
    batch = _create(maker, "kazna.bank_account", [_item(bank_account_item(number=plain))])
    rid, blob = migrator_sql("SELECT id, bank_enc FROM core.manual_entry WHERE batch_id = :b",
                             b=batch.batch_id)[0]
    assert keystore.decrypt_str(Purpose.BANK, bytes(blob),
                                f"core.manual_entry.bank_enc:{rid}") == plain
    with pytest.raises(Exception):  # noqa: B017 -- boshqa AAD bilan ochilmaydi
        keystore.decrypt_str(Purpose.BANK, bytes(blob), f"core.manual_entry.bank_enc:{rid + 1}")


def _approved_balance(maker) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    """Tasdiqlangan qoldiq yozuvi (to'g'ridan-to'g'ri DB): (entry_id, head.version)."""
    batch = _create(maker, "kazna.balance",
                    [_item(balance_item(BANK, "2026-09-30", "10.00"))], submit=True)
    eid = migrator_sql("SELECT entry_id FROM core.manual_entry WHERE batch_id = :b",
                       b=batch.batch_id)[0][0]
    migrator_sql("UPDATE core.manual_batch SET status = 'approved', decided_by = 1, "
                 "decided_at = now() WHERE batch_id = :b", b=batch.batch_id)
    migrator_sql("UPDATE core.manual_head SET approved_version = 1, pending_batch_id = NULL "
                 "WHERE entry_id = :e", e=eid)
    return eid, 1


def test_stale_expected_version_409(maker) -> None:  # type: ignore[no-untyped-def]
    eid, _ = _approved_balance(maker)
    ok = _create(maker, "kazna.balance",
                 [_item(balance_item(BANK, "2026-09-30", "11.00"), entry_id=eid,
                        expected_version=1)])
    assert ok.status == "draft"
    with pytest.raises(ConflictError) as exc:
        _create(maker, "kazna.balance",
                [_item(balance_item(BANK, "2026-09-30", "12.00"), entry_id=eid,
                       expected_version=0)])
    assert exc.value.code == "conflict_modified"


def test_pending_change_409(maker) -> None:  # type: ignore[no-untyped-def]
    eid, _ = _approved_balance(maker)
    _create(maker, "kazna.balance",
            [_item(balance_item(BANK, "2026-09-30", "11.00"), entry_id=eid, expected_version=1)])
    with pytest.raises(ConflictError) as exc:
        _create(maker, "kazna.balance",
                [_item(balance_item(BANK, "2026-09-30", "12.00"), entry_id=eid,
                       expected_version=2)])
    assert exc.value.code == "pending_change"


def test_duplicate_business_key_409(maker) -> None:  # type: ignore[no-untyped-def]
    eid, _ = _approved_balance(maker)
    with pytest.raises(ConflictError) as exc:
        _create(maker, "kazna.balance",
                [_item(balance_item(BANK, "2026-09-01", "99.00"))])
    assert exc.value.code == "duplicate_record" and exc.value.params["entry_id"] == eid


def test_reason_required_for_correction(maker) -> None:  # type: ignore[no-untyped-def]
    eid, _ = _approved_balance(maker)
    batch = _create(maker, "kazna.balance",
                    [_item(balance_item(BANK, "2026-09-30", "11.00"), entry_id=eid,
                           expected_version=1)])
    with pytest.raises(ValidationFailed) as exc:
        run(maker, store.submit_batch, batch.batch_id, expected_version=batch.version,
            reason="  ")
    assert exc.value.code == "reason_required"
    done = run(maker, store.submit_batch, batch.batch_id, expected_version=batch.version,
               reason="Уточнение выписки банка")
    assert done.status == "submitted" and done.reason == "Уточнение выписки банка"
    change = audit_rows("data.batch.submitted")[-1]["details"]["changes"][0]
    assert change["op"] == "change" and change["before"]["balance"] == "10.00"
    assert change["after"]["balance"] == "11.00"


def test_delete_of_approved_makes_tombstone(maker) -> None:  # type: ignore[no-untyped-def]
    eid, _ = _approved_balance(maker)
    batch = _create(maker, "kazna.balance", [store.ItemIn(entry_id=eid, expected_version=1,
                                                          delete=True)])
    row = migrator_sql("SELECT deleted, version FROM core.manual_entry WHERE batch_id = :b",
                       b=batch.batch_id)[0]
    assert row == (True, 2)


def test_withdraw_frees_entries(maker) -> None:  # type: ignore[no-untyped-def]
    eid, _ = _approved_balance(maker)
    batch = _create(maker, "kazna.balance",
                    [_item(balance_item(BANK, "2026-09-30", "11.00"), entry_id=eid,
                           expected_version=1)], submit=True, reason="Уточнение суммы")
    out = run(maker, store.withdraw_batch, batch.batch_id, expected_version=batch.version)
    assert out.status == "withdrawn"
    assert migrator_sql("SELECT pending_batch_id FROM core.manual_head WHERE entry_id = :e",
                        e=eid)[0][0] is None
    again = _create(maker, "kazna.balance",
                    [_item(balance_item(BANK, "2026-09-30", "12.00"), entry_id=eid,
                           expected_version=2)])
    assert again.status == "draft"


def test_update_batch_replaces_draft_items(maker) -> None:  # type: ignore[no-untyped-def]
    first = _create(maker, "kazna.balance", [_item(balance_item(BANK, "2026-09-30", "1.00"))])
    upd = run(maker, store.update_batch, first.batch_id, expected_version=first.version,
              items=[_item(balance_item(BANK, "2026-09-30", "2.00"))])
    assert upd.version == first.version + 1 and upd.rows == 1
    rows = migrator_sql("SELECT payload->>'balance', version FROM core.manual_entry "
                        "WHERE batch_id = :b", b=first.batch_id)
    assert rows == [("2.00", 1)]
    with pytest.raises(ConflictError):
        run(maker, store.update_batch, first.batch_id, expected_version=first.version,
            items=[_item(balance_item(BANK, "2026-09-30", "3.00"))])
    # tashlangan draft'dan biznes-kalit bo'shaydi
    upd2 = run(maker, store.update_batch, first.batch_id, expected_version=upd.version,
               items=[_item(balance_item(BANK, "2026-08-31", "3.00"))])
    other = _create(maker, "kazna.balance", [_item(balance_item(BANK, "2026-09-30", "4.00"))])
    assert upd2.rows == 1 and other.status == "draft"


def test_only_creator_edits_draft(maker, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    batch = _create(maker, "kazna.balance", [_item(balance_item(BANK, "2026-09-30", "1.00"))])
    stranger = ctx_of(make_user("spec_kazna"))
    with pytest.raises(AppError):
        run(stranger, store.submit_batch, batch.batch_id, expected_version=batch.version)


def test_write_permission_required(make_user: MakeUser) -> None:
    seed_dwh_bank(BANK)
    viewer = ctx_of(make_user("profil_sluzhba"))
    with pytest.raises(ForbiddenError):
        _create(viewer, "kazna.balance", [_item(balance_item(BANK, "2026-09-30", "1.00"))])


def test_branch_scope_enforced(make_user: MakeUser) -> None:
    seed_dwh_bank(BANK)
    econ = ctx_of(make_user("economist_filiala", branch_ids=(2,)))
    with pytest.raises(AppError) as exc:
        _create(econ, "kazna.balance",
                [_item(balance_item(BANK, "2026-09-30", "1.00", branch_id=3))], branch_id=3)
    assert exc.value.code == "scope_violation"
    ok = _create(econ, "kazna.balance",
                 [_item(balance_item(BANK, "2026-09-30", "1.00", branch_id=2))], branch_id=2)
    assert ok.branch_id == 2


def test_item_validation_error_is_422_with_rows(maker) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationFailed) as exc:
        _create(maker, "kazna.balance", [_item(balance_item(BANK, "2026-09-30", "1.005"))])
    assert exc.value.code == "invalid_value"
    assert exc.value.params["rows"] == [{"row": 1, "field": "balance", "code": "invalid_value"}]


def test_rate_limited(maker, setting) -> None:  # type: ignore[no-untyped-def]
    from app.core.errors import RateLimitedError

    setting("ratelimit.data_write_per_min", 10)
    with pytest.raises(RateLimitedError):
        for i in range(11):
            _create(maker, "kazna.balance",
                    [_item(balance_item(BANK, f"{2024 + i // 12}-{i % 12 + 1:02d}-28", "1.00"))])


def test_plan_item_flow(maker) -> None:  # type: ignore[no-untyped-def]
    batch = _create(maker, "kazna.payment_plan",
                    [_item(plan_item("PKM54-O09", "2026-09", "10.50"))], submit=True)
    assert batch.status == "submitted"
