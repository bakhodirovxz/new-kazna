"""«Ввод данных»: 5 000 qatorli import -- oldingi holat so'rovi bitta, qo'shish ommaviy."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator

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
