from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from sqlalchemy import text

from app.core import keystore
from app.core.config import get_settings
from app.core.crypto import Purpose, blind_index
from app.dwh.targets import OTHER_OUT_ITEM, TARGETS
from app.etl.db import etl_transaction
from app.etl.staging import DbStagingSink, clear_load
from app.etl.types import Window
from tests.etl_helpers import (
    branch_row,
    cash_row,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)

AUG = Window(date(2026, 8, 1), date(2026, 8, 31))


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def _load(source: str, rows: dict[str, list[dict[str, object]]], **kwargs: Any):
    run_id = open_run(source)
    stage(run_id, source, rows)
    return run_id, {s.target: s for s in merge_all(run_id, source, **kwargs)}


def _cash(source: str) -> list[tuple[str, int, float, str]]:
    with etl_transaction() as conn:
        rows = conn.execute(
            text("SELECT f.src_id, f.date_id, f.amount, i.code FROM dwh.fact_cashflow f "
                 "JOIN dwh.dim_item i USING (item_id) WHERE f.src_system = :s ORDER BY 1, 2"),
            {"s": source},
        ).all()
    return [(r[0], r[1], float(r[2]), r[3]) for r in rows]


def _errors(run_id: int) -> list[tuple[str, str]]:
    with etl_transaction() as conn:
        return [tuple(r) for r in conn.execute(
            text("SELECT severity, code FROM core.etl_error WHERE run_id = :r ORDER BY id"),
            {"r": run_id})]


def test_targets_match_database_columns() -> None:
    with etl_transaction() as conn:
        for name, target in TARGETS.items():
            cols = set(conn.execute(
                text("SELECT column_name FROM information_schema.columns "
                     "WHERE table_schema = 'dwh' AND table_name = :t"), {"t": name}).scalars())
            wanted = set(target.columns) | {lk.column for lk in target.lookups}
            wanted |= {"load_id", "src_system", "updated_at"}
            assert wanted <= cols, (name, wanted - cols)


def test_upsert_is_idempotent_and_updates_only_changes(source: str) -> None:
    tag = new_tag()
    branch = branch_row(tag)
    _, stats = _load(source, {"dim_branch": [branch],
                              "fact_cashflow": [cash_row("d1", 20260805, branch["code"], 100)]})
    assert stats["fact_cashflow"].upserted == 1
    _, stats = _load(source, {"fact_cashflow": [cash_row("d1", 20260805, branch["code"], 100)]})
    assert stats["fact_cashflow"].upserted == 0
    _, stats = _load(source, {"fact_cashflow": [cash_row("d1", 20260805, branch["code"], 120)]})
    assert stats["fact_cashflow"].upserted == 1
    assert _cash(source) == [("d1", 20260805, 120.0, OTHER_OUT_ITEM)]


def test_duplicate_rows_in_one_batch_last_wins(source: str) -> None:
    branch = branch_row(new_tag())
    _load(source, {"dim_branch": [branch], "fact_cashflow": [
        cash_row("dup", 20260805, branch["code"], 10),
        cash_row("dup", 20260805, branch["code"], 30),
    ]})
    assert _cash(source) == [("dup", 20260805, 30.0, OTHER_OUT_ITEM)]


def test_moved_document_date_does_not_duplicate(source: str) -> None:
    branch = branch_row(new_tag())
    _load(source, {"dim_branch": [branch],
                   "fact_cashflow": [cash_row("mv", 20260805, branch["code"], 10)]})
    _load(source, {"fact_cashflow": [cash_row("mv", 20260910, branch["code"], 10)]})
    assert _cash(source) == [("mv", 20260910, 10.0, OTHER_OUT_ITEM)]


def test_unknown_item_goes_to_other_with_warning(source: str) -> None:
    branch = branch_row(new_tag())
    run_id, stats = _load(source, {"dim_branch": [branch], "fact_cashflow": [
        cash_row("in1", 20260805, branch["code"], 5, direction="in", item_code="NO-SUCH"),
        cash_row("out1", 20260805, branch["code"], 7, item_code="NO-SUCH"),
    ]})
    assert stats["fact_cashflow"].warnings == 2
    assert _cash(source) == [("in1", 20260805, 5.0, "PKM54-I06"),
                             ("out1", 20260805, 7.0, "PKM54-O09")]
    assert _errors(run_id) == [("warning", "missing_item"), ("warning", "missing_item")]


def test_unknown_branch_is_skipped_with_error(source: str) -> None:
    run_id, stats = _load(source, {"fact_cashflow": [cash_row("x", 20260805, "NO-BRANCH", 5)]})
    assert stats["fact_cashflow"].upserted == 0
    assert stats["fact_cashflow"].errors == 1
    assert _errors(run_id) == [("error", "missing_branch")]


def test_unknown_counterparty_is_missing_dim(source: str) -> None:
    branch = branch_row(new_tag())
    run_id, stats = _load(source, {"dim_branch": [branch], "fact_cashflow": [
        cash_row("c1", 20260805, branch["code"], 5, cp_code="NO-CP"),
        cash_row("c2", 20260805, branch["code"], 5),
    ]})
    assert stats["fact_cashflow"].upserted == 1
    assert _errors(run_id) == [("error", "missing_dim")]


def test_date_outside_calendar_is_missing_dim(source: str) -> None:
    branch = branch_row(new_tag())
    run_id, _ = _load(source, {"dim_branch": [branch],
                               "fact_cashflow": [cash_row("old", 20100105, branch["code"], 5)]})
    assert _cash(source) == []
    assert ("error", "missing_dim") in _errors(run_id)


def test_window_replace_deletes_missing_documents(source: str) -> None:
    branch = branch_row(new_tag())
    _load(source, {"dim_branch": [branch], "fact_cashflow": [
        cash_row("a", 20260805, branch["code"], 1),
        cash_row("b", 20260806, branch["code"], 2),
        cash_row("c", 20260915, branch["code"], 3),
    ]})
    _, stats = _load(source, {"fact_cashflow": [cash_row("a", 20260805, branch["code"], 1)]},
                     window=AUG, complete=["fact_cashflow"])
    assert stats["fact_cashflow"].deleted == 1
    assert [r[0] for r in _cash(source)] == ["a", "c"]  # c oynadan tashqarida — tegilmaydi


def test_counterparty_inn_encrypted_with_blind_index(source: str) -> None:
    code = f"CP-{new_tag()}"
    run_id = open_run(source)
    with etl_transaction() as conn:
        clear_load(conn, run_id)
        sink = DbStagingSink(conn, run_id, source)
        sink.add("dim_counterparty", {"code": code, "name": "ООО «Тест»", "kind": "supplier",
                                      "inn": "305 123 456"})
        sink.close()
        staged = conn.execute(text("SELECT payload::text FROM stg.rows WHERE load_id = :l"),
                              {"l": run_id}).scalar_one()
    assert "305 123 456" not in staged and "305123456" not in staged
    merge_all(run_id, source)
    with etl_transaction() as conn:
        enc, bidx = conn.execute(
            text("SELECT inn_enc, inn_bidx FROM dwh.dim_counterparty WHERE code = :c"),
            {"c": code}).one()
    aad = f"dwh.dim_counterparty.inn_enc:{code}"
    assert keystore.decrypt_str(Purpose.PII, bytes(enc), aad) == "305 123 456"
    expected = blind_index(get_settings().key_bytes("blind_index_key"), "inn", "305123456")
    assert bytes(bidx) == expected


def test_branch_capacity_change_creates_scd_version(source: str) -> None:
    tag = new_tag()
    _load(source, {"dim_branch": [branch_row(tag, capacity_mw=100)]}, as_of=date(2026, 9, 1))
    _load(source, {"dim_branch": [branch_row(tag, capacity_mw=100)]}, as_of=date(2026, 9, 10))
    _load(source, {"dim_branch": [branch_row(tag, capacity_mw=120)]}, as_of=date(2026, 9, 24))
    with etl_transaction() as conn:
        rows = conn.execute(
            text("SELECT v.capacity_mw, v.valid_from, v.valid_to, v.is_current "
                 "FROM dwh.dim_branch_version v JOIN dwh.dim_branch b USING (branch_id) "
                 "WHERE b.code = :c ORDER BY v.valid_from"), {"c": f"T-{tag}"}).all()
    assert [(float(r[0]), r[1], r[2], r[3]) for r in rows] == [
        (100.0, date(2000, 1, 1), date(2026, 9, 23), False),
        (120.0, date(2026, 9, 24), None, True),
    ]


def test_same_day_scd_change_replaces_version(source: str) -> None:
    tag = new_tag()
    _load(source, {"dim_branch": [branch_row(tag, capacity_mw=100)]}, as_of=date(2026, 9, 1))
    _load(source, {"dim_branch": [branch_row(tag, capacity_mw=110)]}, as_of=date(2026, 9, 24))
    _load(source, {"dim_branch": [branch_row(tag, capacity_mw=130)]}, as_of=date(2026, 9, 24))
    with etl_transaction() as conn:
        rows = conn.execute(
            text("SELECT v.capacity_mw, v.is_current FROM dwh.dim_branch_version v "
                 "JOIN dwh.dim_branch b USING (branch_id) WHERE b.code = :c "
                 "ORDER BY v.valid_from"), {"c": f"T-{tag}"}).all()
    assert [(float(r[0]), r[1]) for r in rows] == [(100.0, False), (130.0, True)]


def test_unknown_target_rejected_by_sink(source: str) -> None:
    run_id = open_run(source)
    with pytest.raises(ValueError, match="staging"), etl_transaction() as conn:
        DbStagingSink(conn, run_id, source).add("users", {"x": 1})
