"""Nashr holati hisoblanadi (paket `approved` bo'lib qoladi, ma'lumot o'chirilmaydi); tuzatish --
mavjud maker-checker oqimi bilan yangi paket."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest

from app import worker
from app.etl import runner as runner_mod
from app.etl.notify import LogNotifier
from app.etl.quality import CheckResult
from app.manual import approval, store
from tests.etl_helpers import purge_source
from tests.helpers import SeedUser
from tests.manual_helpers import balance_item, bank_account_item, ctx_of, migrator_sql, read, run

pytestmark = pytest.mark.usefixtures("clean_manual")
MakeUser = Callable[..., SeedUser]


@pytest.fixture(autouse=True)
def _purge() -> Iterator[None]:
    purge_source("manual")
    yield
    purge_source("manual")


@pytest.fixture
def actors(make_user: MakeUser):  # type: ignore[no-untyped-def]
    return ctx_of(make_user("spec_kazna")), ctx_of(make_user("nach_otdela"))


def _approved(actors, entity: str, items: list[dict[str, Any]], branch: int = 1):  # type: ignore[no-untyped-def]
    maker, checker = actors
    b = run(maker, store.create_batch, entity_id=entity, branch_id=branch, origin="form",
            items=[store.ItemIn(values=v) for v in items], submit=True)
    return run(checker, approval.approve_batch, b.batch_id, expected_version=b.version)


def _pub(ctx, batch_id: int):  # type: ignore[no-untyped-def]
    return read(ctx, store.get_batch, batch_id).publication


def _fail_next_quality(monkeypatch, violations: list[dict[str, Any]]) -> None:  # type: ignore[no-untyped-def]
    real = runner_mod.run_checks
    calls = {"n": 0}

    def fake(*a: Any, **k: Any) -> list[CheckResult]:
        calls["n"] += 1
        if calls["n"] == 1:
            return [CheckResult("balance_identity", False, {"violations": violations})]
        return real(*a, **k)  # type: ignore[no-any-return]

    monkeypatch.setattr(runner_mod, "run_checks", fake)


def test_failed_run_is_shown_and_a_correcting_batch_republishes_everything(  # type: ignore[no-untyped-def]
    actors, monkeypatch
) -> None:
    maker, checker = actors
    acc = _approved(actors, "kazna.bank_account", [bank_account_item()])
    code = str(migrator_sql("SELECT code FROM core.manual_head")[0][0])
    bad = _approved(actors, "kazna.balance", [balance_item(code, "2026-08-31", "500.00")])
    other = _approved(actors, "kazna.payment_plan",
                      [{"branch_code": bank_account_item()["branch_code"],
                        "item_code": "PKM54-O09", "date": "2026-09", "amount": "7.00"}])
    assert _pub(maker, bad.batch_id).status == "queued"

    _fail_next_quality(monkeypatch, [{"branch_id": 1, "month_id": 202608, "diff": "1", "x": "y"},
                                     {"branch_id": 2, "month_id": 202607}])
    assert worker.process_requests(LogNotifier()) == 1

    pub = _pub(maker, bad.batch_id)
    assert pub.status == "failed" and pub.kind == "quality" and pub.run_id
    assert [(c.code, c.items) for c in pub.checks] == [
        ("balance_identity", [{"branch_id": 1, "month_id": 202608}])]  # faqat o'z filiali
    assert _pub(maker, other.batch_id).status == "failed"  # bir yugurish -- bir holat
    # hech narsa o'chirilmadi / o'zgarmadi
    assert migrator_sql("SELECT DISTINCT status FROM core.manual_batch WHERE entity <> 'x' "
                        "AND batch_id = ANY(:b)", b=[bad.batch_id, other.batch_id]) == [
        ("approved",)]
    assert migrator_sql("SELECT count(*) FROM core.manual_head "
                        "WHERE approved_version IS NOT NULL")[0][0] == 3
    listed = read(maker, store.list_batches, box="mine", status="failed").items
    assert {b.batch_id for b in listed} == {acc.batch_id, bad.batch_id, other.batch_id}
    assert all(b.publication and b.publication.status == "failed" for b in listed)

    # tuzatish: yangi paket (maker) + tasdiq (checker) -> yangi yugurish
    eid = int(migrator_sql("SELECT e.entry_id FROM core.manual_entry e WHERE e.batch_id = :b",
                           b=bad.batch_id)[0][0])
    fix_b = run(maker, store.create_batch, entity_id="kazna.balance", branch_id=1,
                origin="form", submit=True, reason="Исправление остатка",
                items=[store.ItemIn(entry_id=eid, expected_version=1,
                                    values=balance_item(code, "2026-08-31", "99.00"))])
    fix = run(checker, approval.approve_batch, fix_b.batch_id, expected_version=fix_b.version)
    assert _pub(maker, fix.batch_id).status == "queued"
    assert _pub(maker, bad.batch_id).status == "failed"  # yangi yugurishgacha

    assert worker.process_requests(LogNotifier()) == 1
    for b in (bad, other, fix):
        pub = _pub(maker, b.batch_id)
        assert pub.status == "published" and pub.build_id, b.batch_id
    from sqlalchemy import text

    from app.etl.db import etl_transaction
    with etl_transaction() as conn:
        vals = [str(v) for v in conn.execute(text(
            "SELECT balance FROM dwh.fact_balance WHERE src_system = 'manual'")).scalars()]
        plans = conn.execute(text(
            "SELECT count(*) FROM dwh.fact_payment_plan WHERE src_system = 'manual'")).scalar_one()
    assert vals == ["99.00"] and plans == 1


def test_build_failure_and_published_by_a_later_run(actors) -> None:  # type: ignore[no-untyped-def]
    maker = actors[0]
    a = _approved(actors, "kazna.bank_account", [bank_account_item()])
    rid = a.etl_request_id
    migrator_sql("UPDATE core.etl_requests SET status = 'failed', error = 'RuntimeError: x' "
                 "WHERE id = :i", i=rid)
    pub = _pub(maker, a.batch_id)
    assert pub.status == "failed" and pub.kind == "build" and "RuntimeError" in (pub.error or "")
    # keyingi so'rov muvaffaqiyatli yugurdi -> avvalgi paket ham nashr qilingan (I2)
    b = _approved(actors, "kazna.bank_account", [bank_account_item()])
    run_id = migrator_sql("INSERT INTO core.etl_run (source, mode, status, build_id) VALUES "
                          "('manual', 'full', 'success', 41) RETURNING id")[0][0]
    migrator_sql("UPDATE core.etl_requests SET status = 'done', run_id = :r WHERE id = :i",
                 r=run_id, i=b.etl_request_id)
    for batch in (a, b):
        p = _pub(maker, batch.batch_id)
        assert (p.status, p.build_id) == ("published", 41)
    assert read(maker, store.list_batches, box="mine", status="failed").items == []
