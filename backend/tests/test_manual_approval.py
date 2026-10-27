from collections.abc import Callable
from typing import Any

import pytest

from app.core.db import apply_rls, new_session
from app.core.errors import AppError, ConflictError, ForbiddenError, ValidationFailed
from app.manual import approval, store
from tests.helpers import SeedUser
from tests.manual_helpers import (
    audit_rows,
    balance_item,
    bank_account_item,
    ctx_of,
    make_role_user,
    migrator_sql,
    run,
    seed_dwh_bank,
)

pytestmark = pytest.mark.usefixtures("clean_manual")
MakeUser = Callable[..., SeedUser]
BANK = "BA-t6bank0000000001"


def _item(values: dict[str, Any], **kw: Any) -> store.ItemIn:
    return store.ItemIn(values=values, **kw)


@pytest.fixture
def maker(make_user: MakeUser):  # type: ignore[no-untyped-def]
    seed_dwh_bank(BANK)
    return ctx_of(make_user("spec_kazna"))


@pytest.fixture
def checker(make_user: MakeUser):  # type: ignore[no-untyped-def]
    return ctx_of(make_user("nach_otdela"))


def _submitted(maker, day: str = "2026-09-30", value: str = "1500.00",  # type: ignore[no-untyped-def]
               entity: str = "kazna.balance", items: list[store.ItemIn] | None = None):
    items = items or [_item(balance_item(BANK, day, value))]
    return run(maker, store.create_batch, entity_id=entity, branch_id=1, origin="form",
               items=items, submit=True)


def _approve(who, batch, **kw: Any):  # type: ignore[no-untyped-def]
    return run(who, approval.approve_batch, batch.batch_id, expected_version=batch.version, **kw)


def test_self_approval_forbidden(maker) -> None:  # type: ignore[no-untyped-def]
    batch = _submitted(maker)
    # maker'ga approve ruxsatini berib ham, o'z paketini tasdiqlay olmaydi
    boss = make_role_user({"data:kazna:approve", "data:kazna:write"}, scope_all=True)
    own = run(ctx_of(boss), store.create_batch, entity_id="kazna.balance", branch_id=1,
              origin="form", items=[_item(balance_item(BANK, "2026-08-31", "5.00"))], submit=True)
    with pytest.raises(ForbiddenError) as exc:
        _approve(ctx_of(boss), own)
    assert exc.value.code == "self_approval_forbidden"
    denied = [r for r in audit_rows("data.batch.approved") if r["result"] == "denied"]
    assert denied and denied[-1]["details"]["error"] == "self_approval_forbidden"
    assert batch.status == "submitted"


def test_approver_needs_permission(maker) -> None:  # type: ignore[no-untyped-def]
    batch = _submitted(maker)
    with pytest.raises(ForbiddenError):
        _approve(maker, batch)  # write bor, approve yo'q


def test_checker_outside_scope_403(maker) -> None:  # type: ignore[no-untyped-def]
    batch = _submitted(maker)  # filial 1
    other = ctx_of(make_role_user({"data:kazna:approve"}, branch_ids=(2,)))
    with pytest.raises(AppError) as exc:
        _approve(other, batch)
    assert exc.value.status_code in (403, 404)  # RLS paketni umuman ko'rsatmaydi


def test_approve_sets_heads_and_queues_one_request(maker, checker) -> None:  # type: ignore[no-untyped-def]
    a = _submitted(maker, "2026-09-30")
    b = _submitted(maker, "2026-08-31", "7.00")
    a2 = _approve(checker, a)
    b2 = _approve(checker, b)
    assert a2.status == "approved" and a2.decided_by == checker.user_id
    assert a2.etl_request_id == b2.etl_request_id is not None
    assert migrator_sql("SELECT count(*) FROM core.etl_requests WHERE source = 'manual' "
                        "AND status = 'pending'")[0][0] == 1
    heads = migrator_sql("SELECT approved_version, approved_deleted, pending_batch_id "
                         "FROM core.manual_head")
    assert heads == [(1, False, None), (1, False, None)]
    ev = audit_rows("data.batch.approved")[-1]["details"]
    assert ev["content_hash"] and ev["etl_request_id"] == b2.etl_request_id


def test_new_request_when_previous_running(maker, checker) -> None:  # type: ignore[no-untyped-def]
    a2 = _approve(checker, _submitted(maker, "2026-09-30"))
    migrator_sql("UPDATE core.etl_requests SET status = 'running' WHERE id = :i",
                 i=a2.etl_request_id)
    b2 = _approve(checker, _submitted(maker, "2026-08-31"))
    assert b2.etl_request_id != a2.etl_request_id


def test_approve_refused_when_period_locked_meanwhile(maker, checker, setting) -> None:  # type: ignore[no-untyped-def]
    batch = _submitted(maker, "2026-08-31")
    setting("manual.locked_through", "2026-08")
    with pytest.raises(ValidationFailed) as exc:
        _approve(checker, batch)
    assert exc.value.code == "period_locked"


def test_stale_version_and_status(maker, checker) -> None:  # type: ignore[no-untyped-def]
    batch = _submitted(maker)
    with pytest.raises(ConflictError):
        run(checker, approval.approve_batch, batch.batch_id, expected_version=batch.version - 1)
    done = _approve(checker, batch)
    with pytest.raises(ValidationFailed) as exc:
        run(checker, approval.approve_batch, done.batch_id, expected_version=done.version)
    assert exc.value.code == "batch_not_editable"


def test_reject_requires_comment(maker, checker) -> None:  # type: ignore[no-untyped-def]
    batch = _submitted(maker)
    with pytest.raises(ValidationFailed) as exc:
        run(checker, approval.reject_batch, batch.batch_id, expected_version=batch.version,
            comment=" ")
    assert exc.value.code == "reason_required" and exc.value.params["fields"] == ["comment"]
    out = run(checker, approval.reject_batch, batch.batch_id, expected_version=batch.version,
              comment="Сумма не сходится с выпиской")
    assert out.status == "rejected" and out.decision_comment
    assert migrator_sql("SELECT pending_batch_id, approved_version FROM core.manual_head") == [
        (None, None)]
    assert migrator_sql("SELECT count(*) FROM core.etl_requests")[0][0] == 0
    with pytest.raises(ForbiddenError):  # rad etishda ham o'ziga qarshi
        run(maker, approval.reject_batch, batch.batch_id, expected_version=out.version,
            comment="qayta")


def test_content_tamper_detected(maker, checker) -> None:  # type: ignore[no-untyped-def]
    batch = _submitted(maker)
    migrator_sql("ALTER TABLE core.manual_entry DISABLE TRIGGER manual_entry_guard")
    try:
        migrator_sql("UPDATE core.manual_entry SET payload = jsonb_set(payload, '{balance}', "
                     "'\"999999.00\"') WHERE batch_id = :b", b=batch.batch_id)
    finally:
        migrator_sql("ALTER TABLE core.manual_entry ENABLE TRIGGER manual_entry_guard")
    with pytest.raises(ConflictError) as exc:
        _approve(checker, batch)
    assert exc.value.code == "conflict_modified"


def test_reference_in_use(maker, checker) -> None:  # type: ignore[no-untyped-def]
    acc = _approve(checker, run(maker, store.create_batch, entity_id="kazna.bank_account",
                                branch_id=1, origin="form", items=[_item(bank_account_item())],
                                submit=True))
    code, eid = migrator_sql("SELECT code, entry_id FROM core.manual_head")[0]
    _approve(checker, _submitted(maker, items=[_item(balance_item(code, "2026-09-30", "10"))]))
    delete = run(maker, store.create_batch, entity_id="kazna.bank_account", branch_id=1,
                 origin="form", items=[store.ItemIn(entry_id=eid, expected_version=1,
                                                    delete=True)],
                 submit=True, reason="Счёт закрыт")
    with pytest.raises(ValidationFailed) as exc:
        _approve(checker, delete)
    assert exc.value.code == "reference_in_use" and acc.status == "approved"


def test_publication_status(maker, checker) -> None:  # type: ignore[no-untyped-def]
    batch = _approve(checker, _submitted(maker))

    def status() -> tuple[str, int | None]:
        with new_session() as s:
            apply_rls(s, None)
            out = approval.publication_status(s, batch)
            return out.status, out.build_id

    rid = batch.etl_request_id
    assert status() == ("queued", None)
    migrator_sql("UPDATE core.etl_requests SET status = 'running' WHERE id = :i", i=rid)
    assert status() == ("running", None)
    migrator_sql("UPDATE core.etl_requests SET status = 'failed' WHERE id = :i", i=rid)
    assert status() == ("failed", None)
    run_id = migrator_sql(
        "INSERT INTO core.etl_run (source, mode, status, build_id) "
        "VALUES ('manual', 'full', 'success', 41) RETURNING id")[0][0]
    migrator_sql("UPDATE core.etl_requests SET status = 'done', run_id = :r WHERE id = :i",
                 r=run_id, i=rid)
    assert status() == ("published", 41)
    migrator_sql("UPDATE core.etl_run SET status = 'failed_quality' WHERE id = :r", r=run_id)
    assert status() == ("failed", None)
