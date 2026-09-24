"""Umumiy fixture'lar. Testlar HAQIQIY PostgreSQL 16 va Redis'ga qarshi ishlaydi."""

from collections.abc import Iterator

import pytest
import redis as redis_lib
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.bootstrap import bootstrap_runtime
from app.core import keystore
from app.core.config import get_settings
from app.core.db import get_engine, new_session


def _reset_core() -> None:
    """core sxemasidagi barcha jadvallarni tozalaydi (sessiya boshida bir marta)."""
    with get_engine("migrator").begin() as conn:
        tables = (
            conn.execute(
                text(
                    "SELECT format('%I.%I', schemaname, tablename) FROM pg_tables "
                    "WHERE schemaname = 'core' AND tablename NOT IN ('audit_head', 'audit_anchor')"
                )
            )
            .scalars()
            .all()
        )
        if tables:
            conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
        if conn.execute(text("SELECT to_regclass('core.audit_head')")).scalar() is not None:
            conn.execute(
                text(
                    "UPDATE core.audit_head SET last_id = NULL, "
                    "last_hash = decode(repeat('00', 32), 'hex')"
                )
            )
        if conn.execute(text("SELECT to_regclass('core.audit_anchor')")).scalar() is not None:
            conn.execute(
                text(
                    "UPDATE core.audit_anchor SET last_dropped_id = NULL, "
                    "last_dropped_hash = decode(repeat('00', 32), 'hex')"
                )
            )


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    command.upgrade(Config("alembic.ini"), "head")
    _reset_core()
    keystore.invalidate_keyring()
    bootstrap_runtime()


@pytest.fixture
def db() -> Iterator[Session]:
    """ugk_app sessiyasi; test oxirida rollback."""
    session = new_session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(autouse=True)
def _clear_rate_limits() -> None:
    client = redis_lib.Redis.from_url(get_settings().redis_url)
    for key in client.scan_iter("rl:*"):
        client.delete(key)
