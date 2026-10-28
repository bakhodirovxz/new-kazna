"""«Ввод данных»: 5 000 qatorli import -- oldingi holat so'rovi bitta, qo'shish ommaviy."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from datetime import date

import pytest
from sqlalchemy import event

from app.core.db import get_engine
from app.manual import store
from tests.helpers import SeedUser
from tests.manual_helpers import balance_item, ctx_of, migrator_sql, run

pytestmark = pytest.mark.usefixtures("clean_manual")
MakeUser = Callable[..., SeedUser]
ROWS = 5000
MONTHS = [f"{y}-{m:02d}-15" for y in (2025, 2026) for m in range(1, 13)][:20]
BUDGET_SECONDS = 20.0
LINK = (  # hisob <-> 1-filial aloqasi (qoldiq fakti)
    "INSERT INTO dwh.fact_balance (date_id, branch_id, bank_id, balance, load_id, src_system, "
    "doc_type, src_id) SELECT 20260115, 1, bank_id, 0, 0, 'synthetic', 'statement', "
    "'link:' || code FROM dwh.dim_bank WHERE code = ANY(:c) ON CONFLICT DO NOTHING")


@pytest.fixture
def statements() -> Iterator[list[str]]:
    seen: list[str] = []

    def spy(conn, cursor, statement, params, context, executemany):  # type: ignore[no-untyped-def]
        seen.append(statement)

    engine = get_engine("app")
    event.listen(engine, "before_cursor_execute", spy)
    yield seen
    event.remove(engine, "before_cursor_execute", spy)


def test_5000_row_import_batches_prior_lookup_and_inserts(
    make_user: MakeUser, statements: list[str]
) -> None:
    codes = [f"BA-perf{i:05d}" for i in range(ROWS // len(MONTHS) + 1)]
    migrator_sql(
        "INSERT INTO dwh.dim_bank (code, bank_name, currency) "
        "SELECT c, 'Perf', 'UZS' FROM unnest(CAST(:c AS text[])) c ON CONFLICT DO NOTHING",
        c=codes)
    migrator_sql(LINK, c=codes)
    items = [store.ItemIn(values=balance_item(code, day, "10.00"))
             for code in codes for day in MONTHS][:ROWS]
    assert len(items) == ROWS
    maker = ctx_of(make_user("spec_kazna"))

    started = time.monotonic()
    batch = run(maker, store.create_batch, entity_id="kazna.balance", branch_id=1,
                origin="import", items=items)
    created = time.monotonic() - started
    created_stmts = len(statements)
    run(maker, store.submit_batch, batch.batch_id, expected_version=batch.version)
    assert batch.rows == ROWS
    priors = [s for s in statements if "p.version" in s and "manual_entry" in s]
    assert len(priors) <= 2, len(priors)  # N+1 emas
    assert created_stmts < 200, created_stmts  # qator boshiga bir nechta so'rov emas
    assert created < BUDGET_SECONDS, created


def test_bulk_new_deduplicates_keys(make_user: MakeUser) -> None:
    from app.core.db import apply_rls, new_session
    from app.manual.entities import ENTITIES

    maker = ctx_of(make_user("spec_kazna"))
    migrator_sql("INSERT INTO dwh.dim_bank (code, bank_name, currency) VALUES "
                 "('BA-dup0001', 'D', 'UZS') ON CONFLICT DO NOTHING")
    migrator_sql(LINK, c=["BA-dup0001"])
    first = run(maker, store.create_batch, entity_id="kazna.balance", branch_id=1,
                origin="form", items=[store.ItemIn(values=balance_item("BA-dup0001",
                                                                      "2026-01-15", "1.00"))])
    entity = ENTITIES["kazna.balance"]

    def planned(day: str) -> store._Planned:
        p = store._Planned(store.ItemIn(), None, None)
        p.values = {**balance_item("BA-dup0001", day, "2.00"), "date": date.fromisoformat(day)}
        return p

    with new_session() as s:
        apply_rls(s, maker.branch_ids)
        done = store._bulk_new(s, maker, entity, first.batch_id, 1,
                               [(1, planned("2026-03-10")), (2, planned("2026-03-20"))])
        s.rollback()
    assert done == {1}  # bir xil kalit ikki marta kiritilmaydi (ikkinchisi sekin yo'lga)
