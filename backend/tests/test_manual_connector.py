from collections.abc import Callable, Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text

from app import worker
from app.core import keystore
from app.core.crypto import Purpose
from app.etl.connectors import KNOWN_SOURCES, make_connector
from app.etl.db import etl_transaction
from app.etl.notify import LogNotifier
from app.etl.runner import Runner
from app.etl.types import Mode
from app.manual import approval, store
from tests.etl_helpers import purge_source
from tests.helpers import SeedUser
from tests.manual_helpers import (
    audit_dump,
    balance_item,
    bank_account_item,
    ctx_of,
    migrator_sql,
    plan_item,
    run,
)

pytestmark = pytest.mark.usefixtures("clean_manual")
MakeUser = Callable[..., SeedUser]
PLAIN = "20208000777766665555"


@pytest.fixture(autouse=True)
def _purge_manual() -> Iterator[None]:
    purge_source("manual")
    yield
    purge_source("manual")


@pytest.fixture
def actors(make_user: MakeUser):  # type: ignore[no-untyped-def]
    return ctx_of(make_user("spec_kazna")), ctx_of(make_user("nach_otdela"))


def _batch(maker, checker, entity: str, items: list[dict[str, Any]], **kw: Any):  # type: ignore[no-untyped-def]
    b = run(maker, store.create_batch, entity_id=entity, branch_id=1, origin="form",
            items=[store.ItemIn(values=v) for v in items], submit=True, **kw)
    return run(checker, approval.approve_batch, b.batch_id, expected_version=b.version)


def _run_manual() -> Any:
    return Runner(make_connector("manual"), mode=Mode.FULL, notifier=LogNotifier()).run()


def _dwh(sql: str) -> list[tuple[Any, ...]]:
    with etl_transaction() as conn:
        return [tuple(r) for r in conn.execute(text(sql)).all()]


def _balances() -> list[tuple[Decimal, int]]:
    return _dwh("SELECT balance, date_id FROM dwh.fact_balance WHERE src_system = 'manual' "
                "ORDER BY date_id")  # type: ignore[return-value]


def _account(actors, number: str = PLAIN) -> str:  # type: ignore[no-untyped-def]
    maker, checker = actors
    _batch(maker, checker, "kazna.bank_account", [bank_account_item(number=number)])
    return str(migrator_sql("SELECT code FROM core.manual_head")[0][0])


def test_manual_is_a_known_source() -> None:
    assert "manual" in KNOWN_SOURCES
    assert make_connector("manual").source == "manual"


def test_approved_rows_reach_dwh_and_deleted_leave(actors) -> None:  # type: ignore[no-untyped-def]
    maker, checker = actors
    code = _account(actors)
    bal = _batch(maker, checker, "kazna.balance", [balance_item(code, "2026-09-30", "1500.00")])
    result = _run_manual()
    assert result.status == "success", result.error
    assert _balances() == [(Decimal("1500.00"), 20260930)]
    eid = migrator_sql("SELECT entry_id FROM core.manual_head WHERE entity = 'kazna.balance'"
                       )[0][0]
    d = run(maker, store.create_batch, entity_id="kazna.balance", branch_id=1, origin="form",
            items=[store.ItemIn(entry_id=eid, expected_version=1, delete=True)], submit=True,
            reason="Ошибочная запись")
    run(checker, approval.approve_batch, d.batch_id, expected_version=d.version)
    assert _run_manual().status == "success"
    assert _balances() == []
    assert bal.status == "approved"


def test_plan_row_with_future_month_kept(actors) -> None:  # type: ignore[no-untyped-def]
    maker, checker = actors
    _batch(maker, checker, "kazna.payment_plan",
           [plan_item("PKM54-O09", "2026-09", "10.5"), plan_item("PKM54-O09", "2027-03", "7")])
    assert _run_manual().status == "success"
    rows = _dwh("SELECT amount, date_id, doc_type FROM dwh.fact_payment_plan "
                "WHERE src_system = 'manual' ORDER BY date_id")
    assert rows == [(Decimal("10.50"), 20260901, "manual_plan"),
                    (Decimal("7.00"), 20270301, "manual_plan")]


def test_drafts_and_rejected_not_extracted(actors) -> None:  # type: ignore[no-untyped-def]
    maker, checker = actors
    code = _account(actors)
    run(maker, store.create_batch, entity_id="kazna.balance", branch_id=1, origin="form",
        items=[store.ItemIn(values=balance_item(code, "2026-09-30", "1.00"))])  # draft
    sub = run(maker, store.create_batch, entity_id="kazna.balance", branch_id=1, origin="form",
              items=[store.ItemIn(values=balance_item(code, "2026-08-31", "2.00"))], submit=True)
    run(checker, approval.reject_batch, sub.batch_id, expected_version=sub.version,
        comment="Не подтверждено выпиской")
    assert _run_manual().status == "success"
    assert _balances() == []


def test_rerun_is_idempotent(actors) -> None:  # type: ignore[no-untyped-def]
    maker, checker = actors
    code = _account(actors)
    _batch(maker, checker, "kazna.balance", [balance_item(code, "2026-09-30", "3.00")])
    assert _run_manual().status == "success"
    second = _run_manual()
    assert second.status == "success"
    ups = _dwh("SELECT rows_upserted FROM core.etl_run WHERE id = " + str(second.run_id))
    assert ups[0][0] == 0


def test_connector_reencrypts_for_staging(actors, caplog) -> None:  # type: ignore[no-untyped-def]
    _account(actors)
    assert _run_manual().status == "success"
    code, last4, enc = _dwh("SELECT code, account_last4, account_enc FROM dwh.dim_bank "
                            "WHERE src_system = 'manual'")[0]
    assert last4 == "5555"
    assert keystore.decrypt_str(Purpose.BANK, bytes(enc),
                                f"dwh.dim_bank.account_enc:{code}") == PLAIN
    leaked = _dwh("SELECT count(*) FROM core.etl_error WHERE message LIKE '%" + PLAIN + "%'")
    assert leaked[0][0] == 0
    steps = _dwh("SELECT count(*) FROM core.etl_step WHERE detail::text LIKE '%" + PLAIN + "%'")
    assert steps[0][0] == 0
    assert PLAIN not in caplog.text and PLAIN not in audit_dump()


def test_other_source_run_keeps_manual_rows(actors) -> None:  # type: ignore[no-untyped-def]
    maker, checker = actors
    code = _account(actors)
    _batch(maker, checker, "kazna.balance", [balance_item(code, "2026-09-30", "4.00")])
    assert _run_manual().status == "success"
    other = Runner(make_connector("synthetic"), mode=Mode.FULL, notifier=LogNotifier()).run()
    assert other.status == "success", other.error
    assert _balances() == [(Decimal("4.00"), 20260930)]
    # va qo'lda yozuv sintetikni ham o'chirmaydi
    assert _dwh("SELECT count(*) FROM dwh.fact_balance WHERE src_system = 'synthetic'")[0][0] > 0


def test_queued_request_processed_by_worker(actors) -> None:  # type: ignore[no-untyped-def]
    maker, checker = actors
    code = _account(actors)
    b = _batch(maker, checker, "kazna.balance", [balance_item(code, "2026-09-30", "5.00")])
    assert worker.process_requests(LogNotifier(), today=date(2026, 9, 30)) >= 1
    req = migrator_sql("SELECT status, run_id FROM core.etl_requests WHERE id = :i",
                       i=b.etl_request_id)[0]
    assert req[0] == "done" and req[1] is not None
    assert _balances() == [(Decimal("5.00"), 20260930)]
    from tests.manual_helpers import read

    pub = read(maker, lambda db, ctx, batch: approval.publication_status(db, batch), b)
    assert pub.status == "published"
