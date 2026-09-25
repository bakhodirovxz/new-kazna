"""Umumiy fixture'lar. Testlar HAQIQIY PostgreSQL 16 va Redis'ga qarshi ishlaydi."""

from collections.abc import Callable, Iterator
from datetime import date

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
from app.dwh import builds
from app.dwh.aggregates import BuildParams, build_all
from app.etl.db import etl_transaction
from app.etl.runner import RunResult
from tests.helpers import SeedUser, create_user


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
        # Fix r1 (M1): `core.data_version`ning yagona tizim qatori endi faqat migratsiya
        # (0007) yoki shu (`ugk_migrator`) ulanish tomonidan seed qilinadi — `ugk_app`da
        # INSERT huquqi yo'q, shuning uchun `ensure_reference()` buni endi qilmaydi.
        if conn.execute(text("SELECT to_regclass('core.data_version')")).scalar() is not None:
            conn.execute(
                text("INSERT INTO core.data_version (id) VALUES (1) ON CONFLICT DO NOTHING")
            )
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
        # crypto_keys yuqorida qayta yaratiladi — eski DEK bilan shifrlangan витрина
        # rekvizitlari o'qib bo'lmaydi. bidx ham NULL: keyingi yuklash qayta shifrlaydi
        # (merge o'zgarishni bidx bo'yicha aniqlaydi).
        if conn.execute(text("SELECT to_regclass('dwh.dim_counterparty')")).scalar() is not None:
            conn.execute(text("UPDATE dwh.dim_counterparty SET inn_enc = NULL, inn_bidx = NULL"))
            conn.execute(text("UPDATE dwh.dim_bank SET account_enc = NULL, account_bidx = NULL"))
        # core.etl_run RESTART IDENTITY bilan tozalandi — run id'lar qayta ishlatiladi,
        # eski staging qatorlari yangi yuklashga "yopishib" qolmasin.
        for table in ("stg.rows", "stg.batch"):
            if conn.execute(text("SELECT to_regclass(:t)"), {"t": table}).scalar() is not None:
                conn.execute(text(f"TRUNCATE {table}"))


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


@pytest.fixture
def make_user() -> Callable[..., SeedUser]:
    return create_user


SYNTHETIC_SEED = 7


@pytest.fixture(scope="session")
def synthetic_run() -> RunResult:
    """Butun sessiya uchun bir marta: sintetik ma'lumotning to'liq yuklanishi (~20–40 s)."""
    from app.etl.runner import Runner
    from app.etl.synthetic import SyntheticConnector
    from app.etl.types import Mode
    from tests.etl_helpers import TEST_AS_OF

    result = Runner(SyntheticConnector(seed=SYNTHETIC_SEED, as_of=TEST_AS_OF),
                    mode=Mode.FULL, today=TEST_AS_OF, sleep=lambda _: None).run()
    assert result.status == "success", result
    return result


@pytest.fixture
def published_synthetic(synthetic_run: RunResult) -> int:
    """Aktiv build'da sintetik ma'lumot bo'lishini kafolatlaydi (boshqa testlar bo'sh
    build publish qilgan bo'lishi mumkin)."""
    from tests.etl_helpers import TEST_AS_OF

    with etl_transaction() as conn:
        build_id = builds.create_build(conn, synthetic_run.run_id)
        build_all(conn, build_id, BuildParams(as_of=TEST_AS_OF, date_from=date(2024, 1, 1)))
        builds.mark_ready(conn, build_id)
        builds.publish(conn, build_id, keep=3)
    return build_id
