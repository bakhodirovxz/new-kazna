"""Ручной пакет, не прошедший проверки качества при публикации: статус «failed» («Ошибка
публикации»), откат голов к последней опубликованной версии, остальные пакеты публикуются."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy.exc import DBAPIError

from app import worker
from app.core.db import apply_rls, new_session
from app.etl.notify import LogNotifier
from app.etl.runner import RunResult
from app.manual import approval, publication, store
from tests.etl_helpers import purge_source
from tests.helpers import SeedUser
from tests.manual_helpers import (
    audit_rows,
    balance_item,
    bank_account_item,
    ctx_of,
    migrator_sql,
    run,
)

pytestmark = pytest.mark.usefixtures("clean_manual")
MakeUser = Callable[..., SeedUser]
ERROR = "Проверки качества не пройдены: balance_identity"


@pytest.fixture(autouse=True)
def _purge() -> Iterator[None]:
    purge_source("manual")
    yield
    purge_source("manual")


@pytest.fixture
def actors(make_user: MakeUser):  # type: ignore[no-untyped-def]
    return ctx_of(make_user("spec_kazna")), ctx_of(make_user("nach_otdela"))


def _approved(actors, entity: str, items: list[dict[str, Any]]):  # type: ignore[no-untyped-def]
    maker, checker = actors
    b = run(maker, store.create_batch, entity_id=entity, branch_id=1, origin="form",
            items=[store.ItemIn(values=v) for v in items], submit=True)
    return run(checker, approval.approve_batch, b.batch_id, expected_version=b.version)


def _fail_run(request_id: int) -> int:
    run_id = int(migrator_sql(
        "INSERT INTO core.etl_run (source, mode, status) VALUES ('manual', 'full', "
        "'failed_quality') RETURNING id")[0][0])
    migrator_sql("UPDATE core.etl_requests SET status = 'failed', run_id = :r WHERE id = :i",
                 r=run_id, i=request_id)
    return run_id


def _status(batch_id: int) -> tuple[str, str | None]:
    return migrator_sql("SELECT status, publish_error FROM core.manual_batch WHERE batch_id = :b",
                        b=batch_id)[0]  # type: ignore[return-value]


def test_failed_batch_is_marked_heads_revert_and_later_batch_publishes(actors) -> None:  # type: ignore[no-untyped-def]
    maker, checker = actors
    acc = _approved(actors, "kazna.bank_account", [bank_account_item()])
    code = str(migrator_sql("SELECT code FROM core.manual_head")[0][0])
    # 1-paket nashr qilindi (so'rov muvaffaqiyatli)
    good = _approved(actors, "kazna.balance", [balance_item(code, "2026-08-31", "5.00")])
    ok_run = int(migrator_sql("INSERT INTO core.etl_run (source, mode, status) VALUES "
                              "('manual', 'full', 'success') RETURNING id")[0][0])
    migrator_sql("UPDATE core.etl_requests SET status = 'done', run_id = :r", r=ok_run)
    # tuzatish paketi (v2) nashrda yiqiladi
    eid = int(migrator_sql("SELECT entry_id FROM core.manual_entry e JOIN core.manual_batch b "
                           "USING (batch_id) WHERE b.entity = 'kazna.balance'")[0][0])
    bad_b = run(maker, store.create_batch, entity_id="kazna.balance", branch_id=1, origin="form",
                items=[store.ItemIn(entry_id=eid, expected_version=1,
                                    values=balance_item(code, "2026-08-31", "99.00"))],
                submit=True, reason="Исправление остатка")
    bad = run(checker, approval.approve_batch, bad_b.batch_id, expected_version=bad_b.version)
    run_id = _fail_run(int(bad.etl_request_id))  # type: ignore[arg-type]
    later = _approved(actors, "kazna.bank_account", [bank_account_item()])  # keyingi so'rov

    failed = publication.fail_unpublished(int(bad.etl_request_id), run_id, ERROR)  # type: ignore[arg-type]

    assert failed == [bad.batch_id]
    status, err = _status(bad.batch_id)
    assert status == "failed" and err is not None and "balance_identity" in err
    assert _status(good.batch_id)[0] == "approved" and _status(later.batch_id)[0] == "approved"
    assert _status(acc.batch_id)[0] == "approved"
    head = migrator_sql("SELECT approved_version, version, pending_batch_id FROM core.manual_head "
                        "WHERE entry_id = :e", e=eid)[0]
    assert tuple(head) == (1, 2, None)  # nashr qilingan v1 ga qaytdi
    ev = audit_rows("data.batch.publish_failed")
    assert len(ev) == 1 and ev[0]["details"]["batch_id"] == bad.batch_id
    # keyingi nashr: muvaffaqiyatsiz paket yo'q, mustaqil paket nashr qilinadi
    from app.etl.connectors import make_connector
    from app.etl.runner import Runner
    from app.etl.types import Mode
    res = Runner(make_connector("manual"), mode=Mode.FULL, notifier=LogNotifier()).run()
    assert res.status == "success", res.error
    vals = migrator_sql("SELECT count(*) FROM core.manual_head WHERE approved_version IS NOT NULL")
    assert vals[0][0] == 3


def test_new_record_of_failed_batch_has_no_approved_version(actors) -> None:  # type: ignore[no-untyped-def]
    acc = _approved(actors, "kazna.bank_account", [bank_account_item()])
    run_id = _fail_run(int(acc.etl_request_id))  # type: ignore[arg-type]
    publication.fail_unpublished(int(acc.etl_request_id), run_id, ERROR)  # type: ignore[arg-type]
    assert migrator_sql("SELECT approved_version, pending_batch_id FROM core.manual_head")[0] == (
        None, None)
    # detail va publication holati
    maker = actors[0]
    from tests.manual_helpers import read
    detail = read(maker, store.get_batch, acc.batch_id)
    assert detail.status == "failed" and "balance_identity" in (detail.publish_error or "")
    with new_session() as s:
        apply_rls(s, None)
        assert approval.publication_status(s, detail).status == "failed"
    # maker yangi paket bilan qayta kirita oladi (bosh bo'sh)
    again = run(maker, store.create_batch, entity_id="kazna.bank_account", branch_id=1,
                origin="form", items=[store.ItemIn(values=bank_account_item())])
    assert again.status == "draft"


def test_only_the_etl_role_can_fail_a_batch(actors) -> None:  # type: ignore[no-untyped-def]
    acc = _approved(actors, "kazna.bank_account", [bank_account_item()])
    with new_session() as s, pytest.raises(DBAPIError):
        apply_rls(s, None)
        s.execute(__import__("sqlalchemy").text(
            "UPDATE core.manual_batch SET status = 'failed' WHERE batch_id = :b"),
            {"b": acc.batch_id})


def test_worker_marks_batches_after_a_quality_failure(actors, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    acc = _approved(actors, "kazna.bank_account", [bank_account_item()])

    class StubRunner:
        def __init__(self, *a: Any, **k: Any) -> None: ...

        def run(self) -> RunResult:
            rid = int(migrator_sql("INSERT INTO core.etl_run (source, mode, status) VALUES "
                                   "('manual', 'full', 'failed_quality') RETURNING id")[0][0])
            return RunResult(rid, "failed_quality", None, ERROR)

    monkeypatch.setattr(worker, "Runner", StubRunner)
    assert worker.process_requests(LogNotifier()) == 1
    assert _status(acc.batch_id)[0] == "failed"
