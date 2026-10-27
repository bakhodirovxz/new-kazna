"""0022: core.manual_* -- FORCE RLS + WITH CHECK, SoD CHECK, append-only, grantlar."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.orm import Session

from app.core import keystore
from app.core.crypto import Purpose
from app.core.db import apply_rls, get_engine, new_session
from app.core.reencrypt import REGISTRY, versions_in_use

NEW_BATCH = (
    "INSERT INTO core.manual_batch (entity, branch_id, origin, created_by) "
    "VALUES ('kazna.balance', :b, 'form', 1) RETURNING batch_id"
)


@contextmanager
def _as_app(branch_ids: frozenset[int] | None) -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, branch_ids)
        yield s


def _mk_entry(s: Session, batch_id: int, *, branch: int = 2, key: str = "k") -> tuple[int, int]:
    entry_id = s.execute(text(
        "INSERT INTO core.manual_head (entity, branch_id, business_key, version) "
        "VALUES ('kazna.balance', :b, :k, 1) RETURNING entry_id"), {"b": branch, "k": key}
    ).scalar_one()
    row_id = s.execute(text(
        "INSERT INTO core.manual_entry (entry_id, version, batch_id, branch_id, payload, "
        "created_by) VALUES (:e, 1, :bt, :b, '{}', 1) RETURNING id"),
        {"e": entry_id, "bt": batch_id, "b": branch}).scalar_one()
    return entry_id, row_id


def _migrator_sql(sql: str, **params: object) -> list[tuple[object, ...]]:
    with get_engine("migrator").begin() as conn:
        conn.execute(text("SELECT set_config('app.scope_all', 'on', true)"))
        res = conn.execute(text(sql), params)
        return [tuple(r) for r in res.all()] if res.returns_rows else []


def test_rls_with_check_blocks_foreign_branch() -> None:
    with _as_app(frozenset({2})) as s:
        with pytest.raises(DBAPIError, match="row-level security"):
            s.execute(text(NEW_BATCH), {"b": 3})
        s.rollback()
        apply_rls(s, frozenset({2}))  # SET LOCAL rollback bilan ketadi
        s.execute(text(NEW_BATCH), {"b": 2})  # o'z filiali -- ok
        s.rollback()


def test_foreign_branch_rows_invisible() -> None:
    with _as_app(None) as s:
        bid = s.execute(text(NEW_BATCH), {"b": 3}).scalar_one()
        s.commit()
    with _as_app(frozenset({2})) as s:
        assert s.execute(text("SELECT count(*) FROM core.manual_batch WHERE batch_id = :i"),
                         {"i": bid}).scalar_one() == 0


def test_all_manual_tables_force_rls() -> None:
    rows = _migrator_sql(
        "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'core' AND relname LIKE 'manual\\_%' AND relkind = 'r'")
    assert {r[0] for r in rows} == {"manual_batch", "manual_head", "manual_entry"}
    assert all(r[1] and r[2] for r in rows)


def test_self_approval_blocked_by_check() -> None:
    with _as_app(None) as s:
        bid = s.execute(text(NEW_BATCH), {"b": 2}).scalar_one()
        s.execute(text("UPDATE core.manual_batch SET status = 'submitted' WHERE batch_id = :i"),
                  {"i": bid})
        with pytest.raises(DBAPIError, match="manual_batch_sod"):
            s.execute(text(
                "UPDATE core.manual_batch SET status = 'approved', decided_by = 1, "
                "decided_at = now() WHERE batch_id = :i"), {"i": bid})
        s.rollback()


def test_decision_requires_decider_and_legal_transition() -> None:
    with _as_app(None) as s:
        bid = s.execute(text(NEW_BATCH), {"b": 2}).scalar_one()
        with pytest.raises(DBAPIError, match="illegal transition"):  # draft -> approved
            s.execute(text("UPDATE core.manual_batch SET status = 'approved', decided_by = 2, "
                           "decided_at = now() WHERE batch_id = :i"), {"i": bid})
        s.rollback()
    with _as_app(None) as s:
        bid = s.execute(text(NEW_BATCH), {"b": 2}).scalar_one()
        s.execute(text("UPDATE core.manual_batch SET status = 'submitted' WHERE batch_id = :i"),
                  {"i": bid})
        with pytest.raises(DBAPIError, match="manual_batch_decided"):
            s.execute(text("UPDATE core.manual_batch SET status = 'approved' "
                           "WHERE batch_id = :i"), {"i": bid})
        s.rollback()
    with _as_app(None) as s:
        bid = s.execute(text(NEW_BATCH), {"b": 2}).scalar_one()
        s.execute(text("UPDATE core.manual_batch SET status = 'submitted' WHERE batch_id = :i"),
                  {"i": bid})
        s.execute(text("UPDATE core.manual_batch SET status = 'approved', decided_by = 2, "
                       "decided_at = now() WHERE batch_id = :i"), {"i": bid})
        with pytest.raises(DBAPIError, match="illegal transition"):  # yakuniy holatdan chiqish yo'q
            s.execute(text("UPDATE core.manual_batch SET status = 'draft' WHERE batch_id = :i"),
                      {"i": bid})
        s.rollback()


def test_batch_identity_columns_not_updatable_by_app() -> None:
    with _as_app(None) as s:
        bid = s.execute(text(NEW_BATCH), {"b": 2}).scalar_one()
        with pytest.raises(ProgrammingError, match="permission denied"):
            s.execute(text("UPDATE core.manual_batch SET created_by = 9 WHERE batch_id = :i"),
                      {"i": bid})
        s.rollback()


def test_entry_append_only_except_reencrypt() -> None:
    with _as_app(None) as s:
        bid = s.execute(text(NEW_BATCH), {"b": 2}).scalar_one()
        _, row = _mk_entry(s, bid, key="ao")
        s.execute(text("UPDATE core.manual_batch SET status = 'submitted' WHERE batch_id = :i"),
                  {"i": bid})
        # bank_enc yangilash (reencrypt) -- ruxsat
        s.execute(text("UPDATE core.manual_entry SET bank_enc = '\\x01' WHERE id = :i"), {"i": row})
        with pytest.raises(ProgrammingError, match="permission denied"):  # ustun grant'i yo'q
            s.execute(text("UPDATE core.manual_entry SET payload = '[1]' WHERE id = :i"),
                      {"i": row})
        s.rollback()
    # trigger ikkinchi qatlam: migrator ham payload'ni o'zgartira olmaydi
    with _as_app(None) as s:
        bid = s.execute(text(NEW_BATCH), {"b": 2}).scalar_one()
        _, row = _mk_entry(s, bid, key="ao2")
        s.execute(text("UPDATE core.manual_batch SET status = 'submitted' WHERE batch_id = :i"),
                  {"i": bid})
        s.commit()
    with pytest.raises(DBAPIError, match="append-only"):
        _migrator_sql("UPDATE core.manual_entry SET payload = '[1]' WHERE id = :i", i=row)
    with pytest.raises(DBAPIError, match="cannot be deleted"), _as_app(None) as s:
        s.execute(text("DELETE FROM core.manual_entry WHERE id = :i"), {"i": row})


def test_draft_entry_can_be_deleted_but_heads_never() -> None:
    with _as_app(None) as s:
        bid = s.execute(text(NEW_BATCH), {"b": 2}).scalar_one()
        e, row = _mk_entry(s, bid, key="dd")
        s.execute(text("DELETE FROM core.manual_entry WHERE id = :i"), {"i": row})
        with pytest.raises(ProgrammingError, match="permission denied"):
            s.execute(text("DELETE FROM core.manual_head WHERE entry_id = :i"), {"i": e})
        s.rollback()


def test_etl_reads_but_cannot_write() -> None:
    with get_engine("etl").begin() as conn:
        conn.execute(text("SELECT set_config('app.scope_all', 'on', true)"))
        conn.execute(text("SELECT count(*) FROM core.manual_head"))
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        get_engine("etl").begin() as conn,
    ):
        conn.execute(text("SELECT set_config('app.scope_all', 'on', true)"))
        conn.execute(text("UPDATE core.manual_head SET version = 5"))


def test_app_cannot_write_dwh_facts_or_bank_secret() -> None:
    with new_session() as s:
        with pytest.raises(ProgrammingError, match="permission denied"):
            s.execute(text("SELECT account_enc FROM dwh.dim_bank"))
        s.rollback()
        s.execute(text("SELECT bank_id, code, bank_name, currency, account_last4 "
                       "FROM dwh.dim_bank"))
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("INSERT INTO dwh.fact_balance (src_system) VALUES ('manual')"))


def test_reencrypt_registry_has_manual_columns() -> None:
    cols = {(c.table, c.column, c.role) for c in REGISTRY}
    assert ("core.manual_entry", "bank_enc", "app") in cols
    assert ("core.manual_entry", "pii_enc", "app") in cols


def test_versions_in_use_sees_manual_rows_despite_force_rls() -> None:
    """FORCE RLS migrator'ni ham ko'r qiladi: versions_in_use scope_all o'rnatmasa, kalit
    retire qilinganda manual_entry qatorlari o'qib bo'lmaydigan bo'lib qolardi."""
    with _as_app(None) as s:
        bid = s.execute(text(NEW_BATCH), {"b": 2}).scalar_one()
        _, row = _mk_entry(s, bid, key="vu")
        blob = keystore.encrypt_str(Purpose.BANK, "x", f"core.manual_entry.bank_enc:{row}")
        s.execute(text("UPDATE core.manual_entry SET bank_enc = :b WHERE id = :i"),
                  {"b": blob, "i": row})
        s.commit()
    with get_engine("migrator").connect() as conn:  # scope_all O'RNATILMAGAN
        assert int.from_bytes(blob[1:3], "big") in versions_in_use(conn, Purpose.BANK)
