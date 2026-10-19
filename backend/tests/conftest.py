"""Umumiy fixture'lar. Testlar HAQIQIY PostgreSQL 16 va Redis'ga qarshi ishlaydi."""

from collections.abc import Callable, Iterator

import pytest
import redis as redis_lib
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Connection
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


def _reset_dwh(conn: Connection) -> None:
    """dwh/mart/stg test holatini tozalaydi (migratsiya seed'lari qoladi).

    Sabab (task-9 C1): `ugk_etl` yuklagan fakt/o'lchovlar sessiyalar orasida DB'da qoladi
    (core tozalanadi, dwh yo'q) — qayta ishga tushirishda eski sintetik fakt'lar yangi
    testlarning build'iga aralashib, cheklarni buzardi. `ugk_etl`da TRUNCATE huquqi yo'q,
    shuning uchun migrator ulanishi. Seed: dim_branch 1..16 (+versiyalari), tizim
    statyalari PKM54-I06/O09, dim_date."""
    tables = conn.execute(text(
        "SELECT format('%I.%I', n.nspname, c.relname) FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE c.relkind IN ('r', 'p') AND NOT c.relispartition AND ("
        "  (n.nspname = 'dwh' AND (c.relname ~ '^fact_' OR c.relname IN ('fx_rate', "
        "   'dim_contract', 'dim_loan_version', 'dim_loan', 'dim_object', 'dim_counterparty', "
        "   'dim_bank', 'dim_nomenclature', 'dim_source', 'dim_position'))) "
        "  OR n.nspname = 'mart')")).scalars().all()
    conn.execute(text(f"TRUNCATE {', '.join(tables)}"))
    conn.execute(text("DELETE FROM dwh.dim_branch_version WHERE branch_id > 16"))
    conn.execute(text("DELETE FROM dwh.dim_branch WHERE branch_id > 16"))
    conn.execute(text("DELETE FROM dwh.dim_item WHERE code NOT IN ('PKM54-I06', 'PKM54-O09')"))
    conn.execute(text("UPDATE dwh.dim_branch SET src_system = 'seed'"))
    conn.execute(text("UPDATE dwh.dim_item SET src_system = 'seed'"))


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
        _reset_dwh(conn)
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
def published_synthetic(synthetic_run: RunResult) -> Iterator[int]:
    """Aktiv build'da sintetik ma'lumot bo'lishini kafolatlaydi (boshqa testlar bo'sh
    build publish qilgan bo'lishi mumkin).

    Yon ta'sir: yangi build publish qilinadi (`core.builds`, `core.data_version`).
    Test tugagach oldingi aktiv build (agar hali mavjud bo'lsa) qayta aktivlanadi."""
    from app.core.errors import ConflictError
    from app.etl.synthetic.model import HISTORY_START
    from tests.etl_helpers import TEST_AS_OF

    with etl_transaction() as conn:
        previous = builds.active_build(conn)
        build_id = builds.create_build(conn, synthetic_run.run_id)
        build_all(conn, build_id, BuildParams(as_of=TEST_AS_OF, date_from=HISTORY_START))
        builds.mark_ready(conn, build_id)
        builds.publish(conn, build_id, keep=3)
    yield build_id
    if previous is not None:
        try:
            with etl_transaction() as conn:
                builds.rollback(conn, previous)
        except ConflictError:
            pass  # oldingi build prune qilingan — qayta aktivlash mumkin emas
