"""Security review (I1, I3, I4, M1, M4, M9): DB himoyalari, nashr poygasi, sifat istisnosi, matn."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import worker
from app.core.db import apply_rls, get_engine, new_session
from app.core.errors import ValidationFailed
from app.dwh import builds
from app.dwh.aggregates import BuildParams, build_all
from app.etl.connectors import make_connector
from app.etl.db import etl_transaction
from app.etl.notify import LogNotifier
from app.etl.quality import run_checks
from app.etl.runner import Runner
from app.etl.types import Mode
from app.manual import approval, store
from app.manual.entities import ENTITIES
from app.manual.validate import check_items
from tests.etl_helpers import (
    FULL_WINDOW,
    TEST_AS_OF,
    branch_row,
    cash_row,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)
from tests.helpers import SeedUser
from tests.manual_helpers import (
    balance_item,
    bank_account_item,
    ctx_of,
    migrator_sql,
    run,
    seed_dwh_bank,
)

pytestmark = pytest.mark.usefixtures("clean_manual")
MakeUser = Callable[..., SeedUser]
BANK = "BA-t9bank0000000001"


@pytest.fixture
def actors(make_user: MakeUser):  # type: ignore[no-untyped-def]
    seed_dwh_bank(BANK)
    return ctx_of(make_user("spec_kazna")), ctx_of(make_user("nach_otdela"))


def _draft_account(maker):  # type: ignore[no-untyped-def]
    return run(maker, store.create_batch, entity_id="kazna.bank_account", branch_id=1,
               origin="form", items=[store.ItemIn(values=bank_account_item())], submit=False)


# --- I1: approved_version faqat tasdiqlangan paketga ishora qila oladi -------------------------


def test_app_cannot_point_approved_version_at_a_draft(actors) -> None:  # type: ignore[no-untyped-def]
    maker, _ = actors
    batch = _draft_account(maker)
    with new_session() as s:
        apply_rls(s, None)
        with pytest.raises(DBAPIError, match="not in an approved batch"):
            s.execute(text("UPDATE core.manual_head SET approved_version = version "
                           "WHERE pending_batch_id = :b"), {"b": batch.batch_id})
        s.rollback()
    heads = migrator_sql("SELECT approved_version FROM core.manual_head")
    assert heads == [(None,)]


def test_submitted_batch_cannot_be_published_by_head_update(actors) -> None:  # type: ignore[no-untyped-def]
    maker, _ = actors
    b = run(maker, store.create_batch, entity_id="kazna.bank_account", branch_id=1,
            origin="form", items=[store.ItemIn(values=bank_account_item())], submit=True)
    with new_session() as s:
        apply_rls(s, None)
        with pytest.raises(DBAPIError, match="not in an approved batch"):
            s.execute(text("UPDATE core.manual_head SET approved_version = version "
                           "WHERE pending_batch_id = :b"), {"b": b.batch_id})
        s.rollback()


def test_connector_refuses_unapproved_version_even_if_trigger_bypassed(actors) -> None:  # type: ignore[no-untyped-def]
    maker, _ = actors
    _draft_account(maker)
    migrator_sql("ALTER TABLE core.manual_head DISABLE TRIGGER manual_head_guard")
    try:
        migrator_sql("UPDATE core.manual_head SET approved_version = version")
        result = Runner(make_connector("manual"), mode=Mode.FULL, notifier=LogNotifier()).run()
    finally:
        migrator_sql("ALTER TABLE core.manual_head ENABLE TRIGGER manual_head_guard")
    assert result.status == "failed"
    with etl_transaction() as conn:
        n = conn.execute(text("SELECT count(*) FROM dwh.dim_bank WHERE src_system = 'manual'"))
        assert n.scalar_one() == 0
    purge_source("manual")


def test_entry_insert_only_into_own_draft(actors) -> None:  # type: ignore[no-untyped-def]
    maker, _ = actors
    b = _draft_account(maker)
    insert = ("INSERT INTO core.manual_entry (entry_id, version, batch_id, branch_id, payload, "
              "created_by) SELECT entry_id, 99, batch_id, 1, '{}', :u FROM core.manual_entry "
              "WHERE batch_id = :b LIMIT 1")
    with new_session() as s:
        apply_rls(s, None)
        with pytest.raises(DBAPIError, match="only the creator"):  # begona foydalanuvchi nomidan
            s.execute(text(insert), {"u": maker.user_id + 1000, "b": b.batch_id})
        s.rollback()
    run(maker, store.submit_batch, b.batch_id, expected_version=b.version)
    with new_session() as s:
        apply_rls(s, None)
        with pytest.raises(DBAPIError, match="only the creator"):  # yuborilgan paketga
            s.execute(text(insert), {"u": maker.user_id, "b": b.batch_id})
        s.rollback()


def test_terminal_batch_is_frozen(actors) -> None:  # type: ignore[no-untyped-def]
    maker, checker = actors
    b = run(maker, store.create_batch, entity_id="kazna.bank_account", branch_id=1,
            origin="form", items=[store.ItemIn(values=bank_account_item())], submit=True)
    done = run(checker, approval.approve_batch, b.batch_id, expected_version=b.version)
    for sql in ("UPDATE core.manual_batch SET content_hash = '\\x00' WHERE batch_id = :b",
                "UPDATE core.manual_batch SET decided_by = decided_by + 1000 WHERE batch_id = :b",
                "UPDATE core.manual_batch SET etl_request_id = 12345 WHERE batch_id = :b"):
        with new_session() as s:
            apply_rls(s, None)
            with pytest.raises(DBAPIError, match=r"frozen|permission"):
                s.execute(text(sql), {"b": done.batch_id})
            s.rollback()


# --- I3: nashr poygasi ------------------------------------------------------------------


def test_worker_claim_waits_for_in_flight_approval(actors) -> None:  # type: ignore[no-untyped-def]
    migrator_sql("INSERT INTO core.etl_requests (source, mode, requested_by) "
                 "VALUES ('manual', 'full', 1)")

    def refuse(_source: str) -> Any:
        raise RuntimeError("test: connector yo'q")

    holder = get_engine("app").connect()
    tx = holder.begin()
    holder.execute(text("SELECT pg_advisory_xact_lock(hashtext('ugk_manual_publish'))"))
    worker_done = threading.Event()

    def claim() -> None:
        worker.process_requests(LogNotifier(), factory=refuse)
        worker_done.set()

    thread = threading.Thread(target=claim, daemon=True)
    thread.start()
    time.sleep(1.5)
    status = migrator_sql("SELECT status FROM core.etl_requests")[0][0]
    assert status == "pending" and not worker_done.is_set()  # tasdiq tugamaguncha claim kutadi
    tx.commit()
    holder.close()
    thread.join(timeout=30)
    assert worker_done.is_set()
    assert migrator_sql("SELECT status FROM core.etl_requests")[0][0] != "pending"


def test_approval_after_claim_creates_new_request(actors) -> None:  # type: ignore[no-untyped-def]
    maker, checker = actors
    b = run(maker, store.create_batch, entity_id="kazna.bank_account", branch_id=1,
            origin="form", items=[store.ItemIn(values=bank_account_item())], submit=True)
    migrator_sql("INSERT INTO core.etl_requests (source, mode, requested_by, status) "
                 "VALUES ('manual', 'full', 1, 'running')")
    done = run(checker, approval.approve_batch, b.batch_id, expected_version=b.version)
    assert migrator_sql("SELECT status FROM core.etl_requests WHERE id = :i",
                        i=done.etl_request_id)[0][0] == "pending"


# --- I4: «Разница» istisnosi faqat shu oy va shu hisob ------------------------------------


@pytest.fixture
def quality_scenario() -> Iterator[tuple[str, int, int, int]]:
    source, tag = new_source(), new_tag()
    branch = branch_row(tag)
    code, system_bank, manual_bank = branch["code"], f"ACC-{tag}", f"BA-q{tag.lower()}0000000"
    rid = open_run(source)
    stage(rid, source, {
        "dim_branch": [branch],
        "dim_bank": [{"code": system_bank, "bank_name": "Тест", "currency": "UZS"}],
        "fact_cashflow": [cash_row("c1", 20260805, code, 100)],
        "fact_balance": [
            {"doc_type": "statement", "src_id": f"s{i}", "date_id": d, "branch_code": code,
             "bank_code": system_bank, "balance": v}
            for i, (d, v) in enumerate([(20260731, 200), (20260831, 100), (20260920, 150)])
        ],
    })
    merge_all(rid, source, FULL_WINDOW)
    mid = open_run("manual")
    stage(mid, "manual", {
        "dim_bank": [{"code": manual_bank, "bank_name": "Рук", "currency": "UZS"}],
        "fact_balance": [
            {"doc_type": "manual_balance", "src_id": f"M:{i}", "date_id": d, "branch_code": code,
             "bank_code": manual_bank, "balance": v}
            for i, (d, v) in enumerate([(20260731, 500), (20260831, 1000)], start=1)
        ],
    })
    merge_all(mid, "manual", FULL_WINDOW)
    with etl_transaction() as conn:
        build_id = builds.create_build(conn, rid)
        build_all(conn, build_id, BuildParams(as_of=TEST_AS_OF, date_from=FULL_WINDOW.date_from))
        builds.mark_ready(conn, build_id)
        branch_id = int(conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                     {"c": code}).scalar_one())
    yield source, rid, build_id, branch_id
    purge_source("manual")
    purge_source(source)


def test_manual_balance_does_not_disable_next_month_check(quality_scenario) -> None:  # type: ignore[no-untyped-def]
    source, rid, build_id, branch_id = quality_scenario
    with etl_transaction() as conn:
        results = run_checks(conn, run_id=rid, build_id=build_id, source=source,
                             window=FULL_WINDOW, totals=None)
    identity = next(r for r in results if r.code == "balance_identity")
    months = {(v["branch_id"], v["month_id"]) for v in identity.detail["violations"]}
    assert (branch_id, 202609) in months  # M+1: tizim hisobi nomuvofiq -- tekshiruv ishlaydi
    assert (branch_id, 202608) not in months  # M: faqat qo'lda hisob hissasi chiqarilgan
    notes = identity.detail["manual_excluded"]
    assert {"branch_id": branch_id, "month_id": 202608, "accounts": 1,
            "reason": "manual_balance"} in notes
    assert all(n["month_id"] != 202609 for n in notes if n["branch_id"] == branch_id)


def test_manual_balance_does_not_hide_system_inconsistency_in_same_month(  # type: ignore[no-untyped-def]
    quality_scenario,
) -> None:
    source, rid, _build_id, branch_id = quality_scenario
    # avgust: tizim hisobi 200 -> 100, oborot 100 (izchil). Oborotni olib tashlab buzamiz.
    with etl_transaction() as conn:
        conn.execute(text("DELETE FROM dwh.fact_cashflow WHERE src_system = :s"), {"s": source})
        build2 = builds.create_build(conn, rid)
        build_all(conn, build2, BuildParams(as_of=TEST_AS_OF, date_from=FULL_WINDOW.date_from))
        builds.mark_ready(conn, build2)
        results = run_checks(conn, run_id=rid, build_id=build2, source=source,
                             window=FULL_WINDOW, totals=None)
    identity = next(r for r in results if r.code == "balance_identity")
    assert (branch_id, 202608) in {(v["branch_id"], v["month_id"])
                                   for v in identity.detail["violations"]}


# --- M1 / M4 --------------------------------------------------------------------------------


def test_trailing_newline_rejected(actors) -> None:  # type: ignore[no-untyped-def]
    del actors
    with new_session() as s:
        apply_rls(s, None)
        item = bank_account_item(number="20208000111122223333\n")
        _, errors = check_items(s, ENTITIES["kazna.bank_account"], 1, [item])
        assert [(e["field"], e["code"]) for e in errors] == [("account_number", "invalid_value")]
        bal = balance_item(BANK, "2026-09-30", "12\n")
        assert check_items(s, ENTITIES["kazna.balance"], 1, [bal])[1]
        bal = balance_item(BANK + "\n", "2026-09-30", "12")
        assert check_items(s, ENTITIES["kazna.balance"], 1, [bal])[1]
        item = bank_account_item()
        item["bank_name"] = "Асакабанк\n"
        assert check_items(s, ENTITIES["kazna.bank_account"], 1, [item])[1]


@pytest.mark.parametrize("bad", ["Причина‮текст", "строка\nвторая", "a⁦b", "x\x00y"])
def test_reason_and_comment_reject_control_and_bidi(actors, bad: str) -> None:  # type: ignore[no-untyped-def]
    maker, checker = actors
    eid_batch = run(maker, store.create_batch, entity_id="kazna.bank_account", branch_id=1,
                    origin="form", items=[store.ItemIn(values=bank_account_item())], submit=True)
    with pytest.raises(ValidationFailed) as exc:
        run(checker, approval.reject_batch, eid_batch.batch_id,
            expected_version=eid_batch.version, comment=bad)
    assert exc.value.code == "invalid_value"
    with pytest.raises(ValidationFailed) as exc:
        run(checker, approval.approve_batch, eid_batch.batch_id,
            expected_version=eid_batch.version, comment=bad)
    assert exc.value.code == "invalid_value"
    draft = run(maker, store.create_batch, entity_id="kazna.bank_account", branch_id=1,
                origin="form", items=[store.ItemIn(values=bank_account_item())], submit=False)
    with pytest.raises(ValidationFailed) as exc:
        run(maker, store.submit_batch, draft.batch_id, expected_version=draft.version, reason=bad)
    assert exc.value.code == "invalid_value"
