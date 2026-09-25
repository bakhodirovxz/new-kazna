import uuid
from collections.abc import Callable, Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app import cli
from app.auth.models import Position, Role
from app.core import keystore
from app.core.config import get_settings
from app.core.crypto import Purpose, blind_index, blob_version
from app.core.db import apply_rls, new_session
from app.core.reencrypt import REGISTRY
from app.dwh.dates import add_months, date_id, from_date_id, month_end, month_id, month_start
from app.etl.db import etl_transaction
from app.main import create_app
from tests.helpers import SeedUser, login


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url="https://testserver") as c:
        yield c


def test_date_helpers() -> None:
    assert date_id(date(2026, 9, 24)) == 20260924
    assert month_id(date(2026, 9, 24)) == 202609
    assert from_date_id(20240229) == date(2024, 2, 29)
    assert month_start(date(2026, 9, 24)) == date(2026, 9, 1)
    assert month_end(date(2024, 2, 10)) == date(2024, 2, 29)
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)


def test_sixteen_branches_seeded() -> None:
    with etl_transaction() as conn:
        rows = conn.execute(
            text("SELECT branch_id, code, kind, capacity_mw FROM dwh.dim_branch "
                 "WHERE branch_id BETWEEN 1 AND 16 ORDER BY branch_id")
        ).all()
        versions = conn.execute(
            text("SELECT count(*) FROM dwh.dim_branch_version WHERE is_current "
                 "AND branch_id BETWEEN 1 AND 16")
        ).scalar_one()
    assert [r.branch_id for r in rows] == list(range(1, 17))
    assert rows[0].kind == "head" and rows[0].capacity_mw is None
    assert rows[1].code == "UGE-02" and float(rows[1].capacity_mw) == 666.0
    assert {r.kind for r in rows[1:]} == {"ges", "cascade"}
    assert versions == 16


def test_dim_date_range_and_workdays() -> None:
    with etl_transaction() as conn:
        first, last = conn.execute(
            text("SELECT min(date_id), max(date_id) FROM dwh.dim_date")
        ).one()
        thursday, saturday = conn.execute(
            text("SELECT (SELECT is_workday FROM dwh.dim_date WHERE date_id = 20260924), "
                 "(SELECT is_workday FROM dwh.dim_date WHERE date_id = 20260926)")
        ).one()
    assert (first, last) == (20150101, 20401231)
    assert thursday is True and saturday is False


def test_system_other_items_exist() -> None:
    with etl_transaction() as conn:
        codes = set(conn.execute(text("SELECT code FROM dwh.dim_item")).scalars())
    assert {"PKM54-I06", "PKM54-O09"} <= codes


def test_branch_rls_for_app_role() -> None:
    with new_session() as s:
        assert s.execute(text("SELECT branch_id FROM dwh.dim_branch")).all() == []
    with new_session() as s:
        apply_rls(s, frozenset({3}))
        assert list(s.execute(text("SELECT branch_id FROM dwh.dim_branch")).scalars()) == [3]


def test_app_role_cannot_write_dims() -> None:
    with new_session() as s, pytest.raises(ProgrammingError, match="permission denied"):
        s.execute(text("INSERT INTO dwh.dim_item (code, name, activity, direction) "
                       "VALUES ('X', 'X', 'operating', 'in')"))


def test_position_branch_fk() -> None:
    with new_session() as s:
        role_id = s.execute(select(Role.id).where(Role.code == "economist_filiala")).scalar_one()
        pos = Position(code=f"p_{uuid.uuid4().hex[:8]}", name="X", role_id=role_id)
        s.add(pos)
        s.flush()
        with pytest.raises(IntegrityError):
            s.execute(text("INSERT INTO core.position_branches VALUES (:p, 999)"), {"p": pos.id})
        s.rollback()


def test_position_with_unknown_branch_is_422(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    login(client, make_user("admin"))
    with new_session() as s:
        econ_id = s.execute(select(Role.id).where(Role.code == "economist_filiala")).scalar_one()
    r = client.post("/api/v1/admin/positions", json={
        "code": f"e_{uuid.uuid4().hex[:6]}", "name": "Экономист", "role_id": econ_id,
        "branch_ids": [3, 999]})
    assert r.status_code == 422
    assert r.json()["error"]["params"]["fields"] == ["branch_ids"]
    assert r.json()["error"]["params"]["missing"] == [999]


def test_registry_includes_dwh_columns() -> None:
    columns = {(c.table, c.column, c.purpose) for c in REGISTRY}
    assert ("dwh.dim_counterparty", "inn_enc", Purpose.PII) in columns
    assert ("dwh.dim_bank", "account_enc", Purpose.BANK) in columns


def test_counterparty_inn_reencrypted_on_pii_rotation() -> None:
    code = f"CP-T{uuid.uuid4().hex[:8]}"
    aad = f"dwh.dim_counterparty.inn_enc:{code}"
    bidx = blind_index(get_settings().key_bytes("blind_index_key"), "inn", "305123456")
    with etl_transaction() as conn:
        conn.execute(
            text("INSERT INTO dwh.dim_counterparty (code, name, kind, inn_enc, inn_bidx, "
                 "src_system) VALUES (:c, 'ООО «Тест»', 'supplier', :e, :b, 'test')"),
            {"c": code, "e": keystore.encrypt_str(Purpose.PII, "305123456", aad), "b": bidx},
        )
    try:
        assert cli.main(["rotate-key", "--purpose", "pii"]) == 0
        keystore.invalidate_keyring()
        with etl_transaction() as conn:
            blob = conn.execute(
                text("SELECT inn_enc FROM dwh.dim_counterparty WHERE code = :c"), {"c": code}
            ).scalar_one()
            active = conn.execute(
                text("SELECT version FROM core.crypto_keys "
                     "WHERE purpose = 'pii' AND status = 'active'")
            ).scalar_one()
        assert blob_version(bytes(blob)) == active
        assert keystore.decrypt_str(Purpose.PII, bytes(blob), aad) == "305123456"
    finally:
        with etl_transaction() as conn:
            conn.execute(text("DELETE FROM dwh.dim_counterparty WHERE code = :c"), {"c": code})
