"""ETL tranzaksiyasi: ugk_etl roli, barcha filiallar doirasi (RLS scope_all)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.db import get_engine

SCOPE_ALL_SQL = (
    "SELECT set_config('app.scope_all', 'on', true), set_config('app.branch_ids', '{}', true)"
)


@contextmanager
def etl_transaction() -> Iterator[Connection]:
    with get_engine("etl").begin() as conn:
        conn.execute(text(SCOPE_ALL_SQL))
        yield conn
