"""Fakt partitsiyalari (spec 4.6).

DDL SECURITY DEFINER funksiyalar orqali — ugk_etl jadval egasi emas.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.dwh.dates import add_months, month_start

PARTITIONED: dict[str, str] = {
    "fact_cashflow": "month",
    "fact_payment_order": "month",
    "fact_balance": "year",
    "fact_debt": "year",
    "fact_generation": "year",
    "fact_stock": "year",
    "fact_stock_move": "year",
}


def ensure_partitions(conn: Connection, table: str, date_from: date, date_to: date) -> int:
    if table not in PARTITIONED:
        raise ValueError(f"partitsiyalanmagan jadval: {table}")
    return int(
        conn.execute(
            text("SELECT dwh.ensure_partitions(:t, :f, :to)"),
            {"t": table, "f": date_from, "to": date_to},
        ).scalar_one()
    )


def ensure_ahead(conn: Connection, today: date, months_ahead: int) -> int:
    """Joriy oydan boshlab `months_ahead` oy oldinga partitsiyalar."""
    end = add_months(month_start(today), months_ahead)
    return sum(ensure_partitions(conn, t, month_start(today), end) for t in PARTITIONED)


def drop_old(conn: Connection, keep_years: int) -> int:
    return int(
        conn.execute(text("SELECT dwh.drop_old_partitions(:k)"), {"k": keep_years}).scalar_one()
    )


def list_partitions(conn: Connection, table: str) -> list[str]:
    return list(
        conn.execute(
            text(
                "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
                "WHERE i.inhparent = to_regclass('dwh.' || :t) ORDER BY c.relname"
            ),
            {"t": table},
        ).scalars()
    )
